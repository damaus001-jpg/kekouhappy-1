import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import hid_rebuild
from hid_rebuild import handle_phone_log, is_digitizer_rejection, rebuild_hid, rebuild_when_idle


class DigitizerRejectionTests(unittest.IsolatedAsyncioTestCase):
    def instance(self, **overrides):
        item = SimpleNamespace(_hid_rebuild_at=0.0, _http_port=8081,
                               _active_service=object(), _ensure_hid=AsyncMock(),
                               _ensure_keyboard=AsyncMock(), _batch_input_generation=0)
        for key, value in overrides.items():
            setattr(item, key, value)
        return item

    def test_matcher(self):
        rejected = ('backboardd: ignoring digitizer event for display <main> from '
                    'unsupported service: (<BKIOHIDService: ...)')
        self.assertTrue(is_digitizer_rejection(rejected))
        self.assertFalse(is_digitizer_rejection('keyboard report delivered'))
        self.assertFalse(is_digitizer_rejection('ignoring digitizer event but a supported service'))

    async def test_rejection_schedules_once_per_cooldown(self):
        import time
        item = self.instance()
        lock = asyncio.Lock()
        message = {'message': 'ignoring digitizer event from unsupported service'}
        with patch('hid_rebuild.rebuild_when_idle', new_callable=AsyncMock) as rebuild, \
                patch('touch_diagnostics.record') as trace:
            self.assertTrue(handle_phone_log(item, lambda i: lock, message))
            await asyncio.sleep(0)
            rebuild.assert_awaited_once()
            trace.assert_called_once()
            # The rebuild completing starts the cooldown; a rejection inside
            # it must not schedule another one.
            item._hid_rebuild_at = time.monotonic()
            self.assertFalse(handle_phone_log(item, lambda i: lock, message))

    async def test_busy_input_lock_skips_rebuild(self):
        item = self.instance()
        lock = asyncio.Lock()
        await lock.acquire()
        with patch('hid_rebuild.LOCK_WAIT_SECONDS', 0.05), \
                patch('hid_rebuild.rebuild_hid', new_callable=AsyncMock) as core:
            await rebuild_when_idle(item, lock)
        core.assert_not_awaited()
        self.assertEqual(item._hid_rebuild_at, 0.0)
        lock.release()

    async def test_standby_media_skips_rebuild(self):
        item = self.instance(_active_service=None)
        lock = asyncio.Lock()
        with patch('hid_rebuild.rebuild_hid', new_callable=AsyncMock) as core:
            await rebuild_when_idle(item, lock)
        core.assert_not_awaited()
        self.assertEqual(item._hid_rebuild_at, 0.0)

    async def test_rebuild_marks_time_and_emits_event(self):
        item = self.instance()
        lock = asyncio.Lock()
        events = []
        with patch('hid_rebuild.rebuild_hid', new_callable=AsyncMock) as core, \
                patch('video_health.event', side_effect=lambda i, r: events.append(r)):
            await rebuild_when_idle(item, lock)
        core.assert_awaited_once_with(item)
        self.assertGreater(item._hid_rebuild_at, 0.0)
        self.assertEqual(events, ['hid-rebuild'])

    async def test_rebuild_hid_clears_connects_registers_and_settles(self):
        item = self.instance()
        with patch('input_health.clear_input', new_callable=AsyncMock) as clear, \
                patch('hid_rebuild.asyncio.sleep', new_callable=AsyncMock) as settle:
            await rebuild_hid(item)
        clear.assert_awaited_once_with(item)
        item._ensure_hid.assert_awaited_once()
        item._ensure_keyboard.assert_awaited_once()
        settle.assert_awaited_once()
        self.assertGreaterEqual(settle.await_args.args[0], 0.5)

    async def test_observer_wiring_dispatches_rejection(self):
        import viewer_patch
        import touch_diagnostics
        viewer_patch.install()
        item = self.instance()
        lock = asyncio.Lock()
        item._batch_input_lock = lock
        message = {'message': 'ignoring digitizer event from unsupported service'}
        with patch('hid_rebuild.rebuild_when_idle', new_callable=AsyncMock) as rebuild, \
                patch('touch_diagnostics.record'):
            self.assertIsNotNone(touch_diagnostics.phone_log_observer)
            self.assertTrue(touch_diagnostics.phone_log_observer(item, message))
            await asyncio.sleep(0)
            rebuild.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
