import asyncio
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, patch

from video_idle import install, pause_if_idle, stream_until_disconnect, touch_media


class MediaIdleTests(unittest.IsolatedAsyncioTestCase):
    def instance(self):
        item = SimpleNamespace(_active_service=object(), _audio_service=object(), _stream_lock=asyncio.Lock(),
            _subscribers={}, _audio_subscribers={}, _rsd=object(), _init_sequence=b'old', _codec_string='old',
            _batch_media_activity=time.monotonic()-10, _stop_hid=AsyncMock())
        async def stop_video(): item._active_service = None
        async def stop_audio(): item._audio_service = None
        item._stop_active_stream = AsyncMock(side_effect=stop_video)
        item._stop_audio_stream = AsyncMock(side_effect=stop_audio)
        return item

    async def test_standby_stops_local_and_remote_media_and_old_input(self):
        item = self.instance()
        with patch('pymobiledevice3.remote.core_device.display_service.DisplayService.stop_all_streams', new_callable=AsyncMock) as remote:
            self.assertTrue(await pause_if_idle(item, asyncio.Lock()))
        remote.assert_awaited_once_with(item._rsd)
        self.assertIsNone(item._active_service)
        self.assertIsNone(item._audio_service)
        self.assertIsNone(item._init_sequence)
        self.assertEqual(item._batch_input_generation, 1)
        item._stop_hid.assert_awaited_once()

    async def test_video_audio_or_background_image_subscriber_keeps_media(self):
        for attr, value in (('_subscribers', {object():object()}), ('_audio_subscribers', {object():None}),
                            ('_jpeg_hub', SimpleNamespace(clients=1))):
            item = self.instance()
            setattr(item, attr, value)
            self.assertFalse(await pause_if_idle(item, asyncio.Lock()))
            item._stop_active_stream.assert_not_awaited()

    async def test_recent_request_and_active_input_prevent_pause(self):
        item = self.instance()
        touch_media(item)
        self.assertFalse(await pause_if_idle(item, asyncio.Lock()))
        item._batch_media_activity -= 10
        lock = asyncio.Lock()
        async with lock:
            self.assertFalse(await pause_if_idle(item, lock))
        item._stop_active_stream.assert_not_awaited()

    async def test_no_eager_media_and_restart_shares_input_lock(self):
        class FakeServer:
            def __init__(self):
                self._active_service = self._audio_service = None
                self._stream_dirty = False
                self.starts = self.audio_starts = 0
            async def _ensure_audio_stream(self):
                self.audio_starts += 1
                self._audio_service = object()
            async def _ensure_fresh_stream(self, force=False):
                self.starts += 1
                self._active_service = object()
            async def serve(self): pass
        lock = asyncio.Lock()
        install(FakeServer, lambda instance: lock)
        item = FakeServer()
        await item._eager_stream_start()
        self.assertEqual(item.starts, 0)
        await lock.acquire()
        task = asyncio.create_task(item._ensure_fresh_stream())
        await asyncio.sleep(0)
        self.assertFalse(task.done())
        lock.release()
        await task
        await item._ensure_fresh_stream()
        self.assertEqual(item.starts, 1)
        self.assertEqual(item.audio_starts, 1)
        await item._ensure_fresh_stream(force=True)
        self.assertEqual(item._batch_input_generation, 1)

    async def test_static_stream_disconnect_cancels_and_releases_subscription(self):
        reader = asyncio.StreamReader()
        entered, released = asyncio.Event(), asyncio.Event()
        async def serving():
            try:
                entered.set()
                await asyncio.Future()
            finally:
                released.set()
        task = asyncio.create_task(stream_until_disconnect(serving(), reader))
        await entered.wait()
        reader.feed_eof()
        await asyncio.wait_for(task, 1)
        self.assertTrue(released.is_set())

    async def test_auth_wait_applies_after_start_but_not_to_warm_stream(self):
        events=[]
        class FakeServer:
            _active_service=None
            _audio_service=object()
            _stream_dirty=False
            async def _ensure_fresh_stream(self, force=False):
                self._active_service=object();events.append('started')
            async def serve(self): pass
        lock=asyncio.Lock()
        install(FakeServer,lambda instance:lock)
        item=FakeServer()
        async def settled(seconds):
            self.assertTrue(lock.locked())
            self.assertEqual(events,['started'])
            self.assertGreaterEqual(seconds,.5)
            events.append('settled')
        with patch('video_idle.asyncio.sleep',side_effect=settled) as wait:
            await item._ensure_fresh_stream()
            await item._ensure_fresh_stream()
        self.assertEqual(events,['started','settled'])
        wait.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
