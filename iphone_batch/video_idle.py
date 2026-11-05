"""Start media on demand and stop receiving standby phones' audio/video."""
import asyncio
import logging
import time

from input_health import clear_input

IDLE_SECONDS = 5


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
            instance._codec_string = None
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
