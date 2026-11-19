from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
import pairing_patch
from pymobiledevice3 import lockdown
from pymobiledevice3.exceptions import NotPairedError
from types import SimpleNamespace


class PairingCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_project_record_uses_current_official_record(self):
        rejected = SimpleNamespace(paired=False, pair_record={'id': 'old'}, close=AsyncMock())
        accepted = SimpleNamespace(paired=True, close=AsyncMock())
        fresh = {'id': 'current'}
        with patch.object(pairing_patch, 'install'), \
             patch.object(lockdown, 'create_using_usbmux', new=AsyncMock(side_effect=[rejected, accepted])) as create, \
             patch('pymobiledevice3.pair_records.get_usbmux_pairing_record', new=AsyncMock(return_value=fresh)), \
             patch('pymobiledevice3.pair_records.get_itunes_pairing_record') as local:
            result = await pairing_patch.open_paired_usb('device', Path('.'))
        self.assertIs(result, accepted)
        rejected.close.assert_awaited_once()
        accepted.close.assert_not_awaited()
        local.assert_not_called()
        self.assertEqual(create.await_args.kwargs['pair_record'], fresh)
        for call in create.await_args_list:
            self.assertFalse(call.kwargs['autopair'])
            self.assertEqual(call.kwargs['serial'], 'device')

    async def test_rejected_distinct_records_close_once_and_report_trust(self):
        old, apple = {'id': 'old'}, {'id': 'apple'}
        clients = [SimpleNamespace(paired=False, pair_record=r, close=AsyncMock()) for r in (old, apple)]
        with patch.object(pairing_patch, 'install'), \
             patch.object(lockdown, 'create_using_usbmux', new=AsyncMock(side_effect=clients)) as create, \
             patch('pymobiledevice3.pair_records.get_usbmux_pairing_record', new=AsyncMock(return_value=old)), \
             patch('pymobiledevice3.pair_records.get_itunes_pairing_record', return_value=apple):
            with self.assertRaisesRegex(pairing_patch.PhoneTrustRequired, '重新连接此设备'):
                await pairing_patch.open_paired_usb('device', Path('.'))
        self.assertEqual(create.await_count, 2)
        for client in clients:
            client.close.assert_awaited_once()

    async def test_background_reconnection_never_autopairs(self):
        original = AsyncMock(); original._project_existing_only = False
        with patch.object(lockdown.LockdownClient, '_handle_autopair', original):
            pairing_patch.prevent_automatic_pairing()
            with self.assertRaises(NotPairedError):
                await lockdown.LockdownClient._handle_autopair(SimpleNamespace(paired=False), True, 10)
            self.assertFalse(original.await_args.args[1])

    async def test_existing_trust_is_used_and_explicit_pair_can_connect_unpaired(self):
        original = AsyncMock(); original._project_existing_only = False
        with patch.object(lockdown.LockdownClient, '_handle_autopair', original):
            pairing_patch.prevent_automatic_pairing()
            await lockdown.LockdownClient._handle_autopair(SimpleNamespace(paired=True), True, 10)
            await lockdown.LockdownClient._handle_autopair(SimpleNamespace(paired=False), False, 10)
            self.assertTrue(all(call.args[1] is False for call in original.await_args_list))

    async def test_project_record_is_preferred_without_repairing(self):
        record={key:'present' for key in ('HostID','HostPrivateKey','HostCertificate','SystemBUID')}
        fallback=AsyncMock();fallback._project_pairing=False
        root=Path(pairing_patch.__file__).resolve().parent/'.device-data'
        with patch.object(lockdown,'get_preferred_pair_record',fallback), patch('pymobiledevice3.pair_records.get_local_pairing_record',return_value=record):
            pairing_patch.install()
            self.assertIs(await lockdown.get_preferred_pair_record('phone',root),record)
            fallback.assert_not_awaited()

    async def test_invalid_cache_falls_back_to_upstream(self):
        fallback=AsyncMock(return_value={'upstream':True});fallback._project_pairing=False
        root=Path(pairing_patch.__file__).resolve().parent/'.device-data'
        with patch.object(lockdown,'get_preferred_pair_record',fallback), patch('pymobiledevice3.pair_records.get_local_pairing_record',return_value={'HostID':'incomplete'}):
            pairing_patch.install()
            self.assertEqual(await lockdown.get_preferred_pair_record('phone',root),{'upstream':True})
            fallback.assert_awaited_once()

    async def test_other_apps_keep_upstream_cache_policy(self):
        fallback=AsyncMock(return_value={'upstream':True});fallback._project_pairing=False
        with patch.object(lockdown,'get_preferred_pair_record',fallback):
            pairing_patch.install()
            await lockdown.get_preferred_pair_record('phone',Path('another-app'))
            fallback.assert_awaited_once()
