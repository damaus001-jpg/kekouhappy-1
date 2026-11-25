"""Detect device-side digitizer rejections and rebuild the HID surfaces.

Backboardd can start dropping CoreDevice digitizer events as "unsupported
service" while every transport-level check stays green (HTTP 200, HID report
delivered to dtuhidd, keyboard health probe fine). Rebuilding the host HID
services gives the device fresh surfaces without restarting the media
session. The rebuild is bounded (short lock wait, cooldown) and never
replays input: the generation bump from clear_input() rejects anything
already in flight.
"""
import asyncio
import logging
import time

DIGITIZER_REJECT_MARKERS = ('ignoring digitizer event', 'unsupported service')
REBUILD_COOLDOWN = 30.0
LOCK_WAIT_SECONDS = 3.0


def is_digitizer_rejection(message):
    """True when a phone log line is backboardd dropping a digitizer event
    from a service it considers unsupported."""
    return bool(message) and all(marker in message for marker in DIGITIZER_REJECT_MARKERS)


def handle_phone_log(instance, input_lock, event):
    """Phone-log observer entry point (event-loop thread). Schedules a bounded
    HID rebuild when the device rejects a digitizer event. Returns True when a
    rebuild was scheduled."""
    if not is_digitizer_rejection(event.get('message') or ''):
        return False
    now = time.monotonic()
    if now - getattr(instance, '_hid_rebuild_at', 0.0) < REBUILD_COOLDOWN:
        logging.getLogger(__name__).debug(
            'digitizer rejection within rebuild cooldown: port=%s',
            getattr(instance, '_http_port', None))
        return False
    from touch_diagnostics import record as trace_record
    trace_record(instance, 'digitizer-rejected', reason='unsupported-service')
    task = asyncio.create_task(rebuild_when_idle(instance, input_lock))
    tasks = getattr(instance, '_hid_rebuild_tasks', None)
    if tasks is None:
        tasks = instance._hid_rebuild_tasks = set()
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return True


async def rebuild_when_idle(instance, input_lock):
    """Rebuild after the input lock is free. A busy lock means the user is
    mid-drag/mid-typing: wait at most LOCK_WAIT_SECONDS, then give up (the
    next rejection retries after the cooldown). Never interrupts input."""
    if time.monotonic() - getattr(instance, '_hid_rebuild_at', 0.0) < REBUILD_COOLDOWN:
        return
    try:
        async with asyncio.timeout(LOCK_WAIT_SECONDS):
            await input_lock.acquire()
    except asyncio.TimeoutError:
        logging.getLogger(__name__).info(
            'HID rebuild skipped: input busy: port=%s', getattr(instance, '_http_port', None))
        return
    try:
        if time.monotonic() - getattr(instance, '_hid_rebuild_at', 0.0) < REBUILD_COOLDOWN:
            return
        if getattr(instance, '_active_service', None) is None:
            # Standby media: no active stream to publish HID surfaces; a
            # digitizer rejection cannot happen here in the first place.
            return
        started = time.monotonic()
        await rebuild_hid(instance)
        instance._hid_rebuild_at = started
        from video_health import event as video_event
        video_event(instance, 'hid-rebuild')
        logging.getLogger(__name__).info(
            'HID rebuilt after digitizer rejection: port=%s elapsed=%.2fs',
            getattr(instance, '_http_port', None), time.monotonic() - started)
    finally:
        input_lock.release()


async def rebuild_hid(instance):
    """Replace UHS/Indigo connections and the keyboard surface, then wait for
    the device to authenticate the fresh surfaces before any new input.

    Media session is left untouched: this addresses the "unsupported service"
    rejection by giving backboardd new HID surfaces, not by churning video.
    """
    from input_health import clear_input
    await clear_input(instance)
    await instance._ensure_hid()
    await instance._ensure_keyboard()
    from pymobiledevice3.remote.core_device import hid_service
    settle = max(.5, getattr(hid_service, 'TOUCH_AUTH_SETTLE_SECONDS', .5))
    await asyncio.sleep(settle)
