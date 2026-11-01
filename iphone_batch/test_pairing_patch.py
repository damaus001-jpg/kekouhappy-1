from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
import pairing_patch
from pymobiledevice3 import lockdown


class PairingCacheTests(unittest.IsolatedAsyncioTestCase):
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
