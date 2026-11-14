import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from video_health import event, install, snapshot, manual_restart, ForwardWriter, record_browser


class VideoHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_reports_are_bounded_numeric_only_and_content_fields_are_rejected(self):
        item,_,_=self.server()
        for i in range(100):
            record_browser(item,{'client':'c'+str(i),'mode':'hevc','state':'streaming',
                                'selected':True,'queue':0,'paint_age_ms':20,'decoded':i})
        self.assertEqual(len(snapshot(item)['browser']),16)
        for report in ({'client':'a','text':'must not store'}, {'client':'a','queue':float('nan')},
                       {'client':'a','queue':-1}, {'client':'a','hidden':'false'}):
            with self.assertRaises(ValueError):record_browser(item,report)
        self.assertNotIn('must not store',str(snapshot(item)))
    def server(self):
        class Server:
            _ensure_fresh_stream = AsyncMock()
            _send_rtcp_pli = AsyncMock()
        fresh, pli = Server._ensure_fresh_stream, Server._send_rtcp_pli
        install(Server)
        instance = Server()
        instance._subscribers = {}
        instance._active_service = object()
        instance._last_good_au_t = 1
        return instance, fresh, pli

    async def test_concurrent_restart_paths_share_cooldown_and_rolling_budget(self):
        item, fresh, _ = self.server()
        with patch('video_health.monotonic', return_value=100):
            await asyncio.gather(*(item._ensure_fresh_stream(force=True) for _ in range(10)))
        self.assertEqual(fresh.await_count, 1)
        for now in (131, 162, 193, 224):
            with patch('video_health.monotonic', return_value=now):
                await item._ensure_fresh_stream(force=True)
        self.assertEqual(fresh.await_count, 3)
        with patch('video_health.monotonic', return_value=401):
            await item._ensure_fresh_stream(force=True)
        self.assertEqual(fresh.await_count, 4)

    async def test_pli_paths_share_rate_limit(self):
        item, _, pli = self.server()
        for now in (100, 100.1, 101, 102, 102.5):
            with patch('video_health.monotonic', return_value=now):
                await item._send_rtcp_pli()
        self.assertEqual(pli.await_count, 2)

    async def test_silent_bootstrap_cannot_restart_but_explicit_restart_can(self):
        item, fresh, _ = self.server()
        item._active_recv_task = SimpleNamespace(done=lambda: False)
        item._subscribers = {asyncio.Queue(): SimpleNamespace(needs_key=True, needs_key_since=2)}
        await item._ensure_fresh_stream(force=True)
        fresh.assert_not_awaited()
        context = manual_restart.set(True)
        try:
            await item._ensure_fresh_stream(force=True)
        finally:
            manual_restart.reset(context)
        fresh.assert_awaited_once()

    async def test_telemetry_is_bounded_and_contains_no_payload(self):
        item, _, _ = self.server()
        item._password = 'secret'
        for _ in range(1000):
            event(item, 'source-ensure')
        data = snapshot(item)
        self.assertEqual(len(data['events']), 128)
        self.assertNotIn('secret', str(data))

    async def test_forward_failure_is_observed_without_retaining_payload(self):
        item, _, _ = self.server()
        writer = SimpleNamespace(write=lambda data: None, drain=AsyncMock(side_effect=ConnectionResetError()))
        observed = ForwardWriter(item, writer)
        observed.write(b'private-video-data')
        with self.assertRaises(ConnectionResetError):
            await observed.drain()
        data = snapshot(item)
        self.assertEqual(data['forwards'][0]['bytes'], len(b'private-video-data'))
        self.assertNotIn('private-video-data', str(data))
        self.assertEqual(data['events'][-1]['reason'], 'forward-failure-ConnectionResetError')

    async def test_static_silence_does_not_restart_but_terminated_reader_does(self):
        for done in (False, True):
            item, fresh, _ = self.server()
            item._active_recv_task = SimpleNamespace(done=lambda: done)
            item._subscribers = {asyncio.Queue(): SimpleNamespace(needs_key=False)}
            calls = 0
            async def tick(_):
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise asyncio.CancelledError()
            with patch('video_health.asyncio.sleep', side_effect=tick):
                with self.assertRaises(asyncio.CancelledError):
                    await item._stall_watchdog()
            self.assertEqual(fresh.await_count, int(done))

    async def test_key_starvation_requires_source_progress(self):
        for last_au in (1, 20):
            item, fresh, _ = self.server()
            item._last_good_au_t = last_au
            item._active_recv_task = SimpleNamespace(done=lambda: False)
            item._subscribers = {asyncio.Queue(): SimpleNamespace(needs_key=True, needs_key_since=2)}
            calls = 0
            async def tick(_):
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise asyncio.CancelledError()
            with patch('video_health.asyncio.sleep', side_effect=tick), patch('video_health.monotonic', return_value=30):
                with self.assertRaises(asyncio.CancelledError):
                    await item._stall_watchdog()
            self.assertEqual(fresh.await_count, int(last_au == 20))


if __name__ == '__main__':
    unittest.main()
