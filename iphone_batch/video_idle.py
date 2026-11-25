"""Start media on demand and stop receiving standby phones' audio/video."""
import asyncio
import logging
import sys
import time

from input_health import clear_input

IDLE_SECONDS = 5


async def audio_recv_keepalive(instance, transport):
    """Windows replacement for upstream ``_audio_udp_recv``: consume the
    device's AAC-ELD RTP without decoding.

    The 8070 page never plays phone audio and Windows has no AudioToolbox, so
    upstream's decoder construction fails there on every start: the receive
    task dies, the idle/wake cycle rebuilds the audio session, and each cycle
    logs a misleading error. The device-side audio session must still exist
    (it pairs with the video session through the shared client_session_id,
    see upstream ``_shared_session_id``), so this task keeps draining RTP and
    maintaining the counters the audio RTCP keepalive uses, then discards the
    payload. No decoder, no error churn, no PCM broadcasts.
    """
    while True:
        try:
            data = await transport.recv(65535)
        except (OSError, asyncio.CancelledError):
            return
        except Exception:
            logging.getLogger(__name__).warning(
                'audio keepalive recv crashed: port=%s',
                getattr(instance, '_http_port', None), exc_info=True)
            return
        if len(data) < 12:
            continue
        payload_type = data[1] & 0x7F
        if 64 <= payload_type <= 95:  # RTCP
            continue
        instance._audio_rtp_packets_received += 1
        seq = int.from_bytes(data[2:4], 'big')
        cur_ext = instance._audio_rtp_highest_seq
        cycles = (cur_ext >> 16) & 0xFFFF
        last_seq16 = cur_ext & 0xFFFF
        if seq < last_seq16 and (last_seq16 - seq) > 0x8000:
            cycles = (cycles + 1) & 0xFFFF
        new_ext = (cycles << 16) | seq
        if cur_ext == 0 or ((new_ext - cur_ext) & 0xFFFFFFFF) < 0x80000000:
            instance._audio_rtp_highest_seq = new_ext


def touch_media(instance):
    instance._batch_media_activity = time.monotonic()


def media_in_use(instance):
    return bool(getattr(instance, '_subscribers', {}) or getattr(instance, '_audio_subscribers', {})
        or getattr(getattr(instance, '_jpeg_hub', None), 'clients', 0))


async def wake_media(instance):
    touch_media(instance)
    await instance._ensure_fresh_stream(force=False)


async def pause_if_idle(instance, input_lock, now=None):
    now = time.monotonic() if now is None else now
    if (media_in_use(instance) or input_lock.locked()
            or now - getattr(instance, '_batch_media_activity', now) < IDLE_SECONDS
            or not (getattr(instance, '_active_service', None) or getattr(instance, '_audio_service', None))):
        return False
    async with input_lock:
        if media_in_use(instance) or time.monotonic() - instance._batch_media_activity < IDLE_SECONDS:
            return False
        async with instance._stream_lock:
            # Detach receive tasks first. No old video is buffered for wakeup.
            async with asyncio.timeout(4):
                await instance._stop_active_stream()
                await instance._stop_audio_stream()
            instance._init_sequence = None
            # Keep the cached codec config (_codec_string + VPS/SPS/PPS): the
            # dashboard readiness polls hit /codec every few seconds and must
            # be answerable without waking standby media. A real stream start
            # re-derives them from the new SPS anyway.
        await clear_input(instance)
        # Stop on a fresh connection: a second reply-bearing call on the
        # connection that started media can crash the device's media daemon.
        from pymobiledevice3.remote.core_device.display_service import DisplayService
        try:
            await asyncio.wait_for(DisplayService.stop_all_streams(instance._rsd), 3)
        except Exception as error:
            logging.getLogger(__name__).warning('Idle media remote cleanup failed: port=%s error=%s',
                getattr(instance, '_http_port', None), type(error).__name__)
        logging.getLogger(__name__).info('Standby media paused: port=%s', getattr(instance, '_http_port', None))
        return True


def ensure_idle_monitor(instance, input_lock):
    if getattr(instance, '_batch_idle_task', None) is not None:
        return
    instance._batch_media_activity = time.monotonic()

    async def monitor():
        while True:
            await asyncio.sleep(1)
            try:
                await pause_if_idle(instance, input_lock)
            except Exception as error:
                logging.getLogger(__name__).warning('Idle media cleanup failed: port=%s error=%s',
                    getattr(instance, '_http_port', None), type(error).__name__)
    instance._batch_idle_task = asyncio.create_task(monitor())


async def stream_until_disconnect(serving, reader):
    """A static phone may send nothing; EOF must still release its subscription."""
    task = asyncio.create_task(serving)
    async def disconnected():
        while not reader.at_eof():
            await asyncio.sleep(.2)
    watcher = asyncio.create_task(disconnected())
    try:
        await asyncio.wait((task, watcher), return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            await task
    finally:
        for pending in (task, watcher):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, watcher, return_exceptions=True)


def install(server_class, input_lock):
    original_fresh = server_class._ensure_fresh_stream
    original_serve = server_class.serve

    async def lazy_start(instance):
        # HTTP readiness needs a live device connection, not 20 eager encoders.
        return None

    async def fresh(instance, force=False):
        touch_media(instance)
        async with input_lock(instance):
            if instance._active_service is not None and not instance._stream_dirty and not force:
                return
            # Serialize media replacement against manual input/health checks.
            # A media restart invalidates all previously queued HID commands.
            if instance._active_service is not None:
                instance._batch_input_generation = getattr(instance, '_batch_input_generation', 0) + 1
            if getattr(instance, '_audio_service', None) is None:
                try:
                    await asyncio.wait_for(instance._ensure_audio_stream(), 4)
                except Exception as error:
                    logging.getLogger(__name__).warning('On-demand audio start failed: %s', type(error).__name__)
            await original_fresh(instance, force=force)
            # Upstream #2036 found 0.3s too short for iPhone 11. Honor its
            # current minimum; pay this only on media setup, never per click.
            from pymobiledevice3.remote.core_device import hid_service
            await asyncio.sleep(max(.5, getattr(hid_service, 'TOUCH_AUTH_SETTLE_SECONDS', .5)))

    async def serve(instance):
        try:
            return await original_serve(instance)
        finally:
            task = getattr(instance, '_batch_idle_task', None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    server_class._eager_stream_start = lazy_start
    server_class._ensure_fresh_stream = fresh
    server_class.serve = serve
    if sys.platform != 'darwin':
        # Windows has no AudioToolbox: upstream's AAC-ELD decoder would fail
        # on every start and kill the receive task. Keep the paired audio
        # session alive by draining RTP without decoding.
        server_class._audio_udp_recv = audio_recv_keepalive
