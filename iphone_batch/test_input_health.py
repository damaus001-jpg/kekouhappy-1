import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from input_health import check_input, clear_input, ensure_input_services, refresh_service_catalog


class InputHealthTests(unittest.IsolatedAsyncioTestCase):
    def instance(self):
        return SimpleNamespace(_ensure_hid=AsyncMock(), _stop_hid=AsyncMock(),
            _ensure_keyboard=AsyncMock(), _kb_service_id=9,
            _uhs=SimpleNamespace(list_connected_services=AsyncMock(return_value={'services': []}), send_keyboard=AsyncMock()))

    async def test_idle_probe_emits_no_pressed_keys_or_touch(self):
        item = self.instance()
        result = await check_input(item, asyncio.Lock(), lambda: True)
        self.assertTrue(result['ok'])
        self.assertFalse(result['recovered'])
        self.assertEqual(result['probe'], 'idle-keyboard')
        item._uhs.list_connected_services.assert_not_awaited()
        item._stop_hid.assert_not_awaited()
        item._uhs.send_keyboard.assert_awaited_once_with(9, [])

    async def test_input_failure_recovers_without_enumerating_services(self):
        item = self.instance()
        item._uhs.send_keyboard.side_effect = [ConnectionError('dead'), None, None]
        result = await check_input(item, asyncio.Lock(), lambda: True)
        self.assertTrue(result['ok'])
        self.assertTrue(result['recovered'])
        self.assertEqual(result['probe'], 'idle-keyboard')
        item._stop_hid.assert_awaited_once()
        self.assertTrue(all(call.args == (9, []) for call in item._uhs.send_keyboard.await_args_list))
        # Further periodic checks must not repeatedly destroy this device's HID.
        result = await check_input(item, asyncio.Lock(), lambda: True)
        self.assertTrue(result['ok'])
        self.assertFalse(result['recovered'])
        item._uhs.list_connected_services.assert_not_awaited()
        item._stop_hid.assert_awaited_once()

    async def test_idle_fallback_never_releases_user_held_keys(self):
        item = self.instance()
        item._batch_keys_down = True
        self.assertEqual((await check_input(item, asyncio.Lock(), lambda: True))['state'], 'busy')
        item._uhs.send_keyboard.assert_not_awaited()

    async def test_dead_connection_recreated_once_then_verified(self):
        item = self.instance()
        item._ensure_hid.side_effect = [ConnectionError('dead'), None]
        result = await check_input(item, asyncio.Lock(), lambda: True)
        self.assertTrue(result['recovered'])
        self.assertTrue(result['ok'])
        self.assertEqual(item._ensure_hid.await_count, 2)
        item._stop_hid.assert_awaited_once()
        self.assertEqual(item._batch_input_generation, 1)
        self.assertFalse(item._batch_recovering)

    async def test_permanent_failure_is_bounded_and_marks_unavailable(self):
        item = self.instance()
        item._uhs.send_keyboard.side_effect = ConnectionError('offline')
        result = await check_input(item, asyncio.Lock(), lambda: True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['state'], 'unavailable')
        self.assertEqual(item._ensure_hid.await_count, 2)
        self.assertEqual(item._stop_hid.await_count, 2)

    async def test_drag_keys_recent_input_and_busy_lock_skip_probe(self):
        for attributes in ({'_batch_contact': {'x': 1}}, {'_batch_keys_down': True},
                           {'_batch_last_input': time.monotonic()}):
            item = self.instance()
            for key, value in attributes.items():
                setattr(item, key, value)
            result = await check_input(item, asyncio.Lock(), lambda: True)
            self.assertEqual(result['state'], 'busy')
            item._ensure_hid.assert_not_awaited()
        item = self.instance()
        lock = asyncio.Lock()
        async with lock:
            self.assertEqual((await check_input(item, lock, lambda: True))['state'], 'busy')
        item._ensure_hid.assert_not_awaited()

    async def test_busy_gesture_reports_age_of_confirmed_input_without_probing(self):
        item=self.instance()
        item._batch_contact={'type':'contact','x':1,'y':2}
        item._batch_last_input=time.monotonic()-.5
        result=await check_input(item,asyncio.Lock(),lambda:True)
        self.assertEqual(result['state'],'busy')
        self.assertGreaterEqual(result['input_confirmed_age'],.5)
        self.assertLess(result['input_confirmed_age'],2)
        item._uhs.send_keyboard.assert_not_awaited()

    async def test_orphan_contact_does_not_claim_recent_confirmed_input(self):
        item=self.instance()
        item._batch_contact={'type':'contact','x':1,'y':2}
        result=await check_input(item,asyncio.Lock(),lambda:True)
        self.assertNotIn('input_confirmed_age',result)

    async def test_busy_dispatch_lock_reports_previous_success_without_sending_input(self):
        item=self.instance()
        item._batch_last_input=time.monotonic()-.2
        lock=asyncio.Lock()
        async with lock:
            result=await check_input(item,lock,lambda:True)
        self.assertEqual(result['state'],'busy')
        self.assertLess(result['input_confirmed_age'],2)
        item._ensure_hid.assert_not_awaited()

    async def test_switching_away_during_failed_probe_does_not_reconnect(self):
        item = self.instance()
        enabled = True
        async def fail():
            nonlocal enabled
            enabled = False
            raise ConnectionError('closed')
        item._ensure_hid.side_effect = fail
        result = await check_input(item, asyncio.Lock(), lambda: enabled)
        self.assertEqual(result['state'], 'inactive')
        self.assertEqual(item._ensure_hid.await_count, 1)

    async def test_inactive_never_connects(self):
        item = self.instance()
        self.assertEqual((await check_input(item, asyncio.Lock(), lambda: False))['state'], 'inactive')
        item._ensure_hid.assert_not_awaited()

    async def test_failed_cleanup_forgets_dead_services(self):
        item = self.instance()
        item._stop_hid.side_effect = OSError('close failed')
        await clear_input(item)
        self.assertIsNone(item._uhs)
        self.assertIsNone(item._indigo)
        self.assertIsNone(item._kb_service_id)

    async def test_canceled_connect_closes_uncached_half_open_service(self):
        entered = asyncio.Event()
        async def connect():
            entered.set()
            await asyncio.Future()
        half = SimpleNamespace(connect=AsyncMock(side_effect=connect), close=AsyncMock())
        item = SimpleNamespace(_hid_lock=asyncio.Lock(), _uhs=None, _indigo=None, _rsd=object())
        with patch('pymobiledevice3.remote.core_device.hid_service.UniversalHIDServiceService', return_value=half):
            task = asyncio.create_task(ensure_input_services(item))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        half.close.assert_awaited_once()
        self.assertIsNone(item._uhs)
        self.assertFalse(item._hid_lock.locked())

    async def test_service_discovery_verifies_device_before_updating_catalog(self):
        original = {'Services': {'old': {'Port': 1}}}
        rsd = SimpleNamespace(service=SimpleNamespace(address=('host', 123)), open_connection=None,
            handshake_uuid='same-host-identity', udid='one', peer_info=original)
        item = SimpleNamespace(_rsd=rsd)
        peer = {'Properties': {'UniqueDeviceID':'wrong-device'}, 'Services': {'new': {'Port':2}}}
        connection = SimpleNamespace(connect=AsyncMock(), close=AsyncMock(), send_device_handshake=AsyncMock(),
            receive_response=AsyncMock(return_value=peer))
        with patch('pymobiledevice3.remote.remotexpc.RemoteXPCConnection', return_value=connection):
            with self.assertRaises(ConnectionError):
                await refresh_service_catalog(item)
            self.assertIs(rsd.peer_info, original)
            peer['Properties']['UniqueDeviceID'] = 'one'
            await refresh_service_catalog(item)
        self.assertIs(rsd.peer_info, peer)
        self.assertEqual(connection.close.await_count, 2)
        connection.send_device_handshake.assert_awaited_with('same-host-identity')

    async def test_connect_failure_refreshes_catalog_without_holding_input_lock(self):
        item = self.instance()
        item._rsd = object()
        item._ensure_hid.side_effect = [asyncio.TimeoutError(), None]
        lock = asyncio.Lock()
        async def refresh(instance):
            self.assertFalse(lock.locked(), 'device switching must remain possible during discovery')
        with patch('input_health.refresh_service_catalog', side_effect=refresh) as repair:
            result = await check_input(item, lock, lambda: True)
        self.assertTrue(result['ok'])
        self.assertTrue(result['discovery_refreshed'])
        repair.assert_awaited_once_with(item)


if __name__ == '__main__':
    unittest.main()
