import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from device_trust import repair

class TrustRepairTests(unittest.IsolatedAsyncioTestCase):
    async def run_repair(self, client, root):
        factory=AsyncMock(return_value=client)
        result=await repair('phone13',root,factory)
        self.assertFalse(factory.call_args.kwargs['autopair'])
        self.assertEqual(factory.call_args.kwargs['serial'],'phone13')
        return result

    def client(self, paired=False):
        client=AsyncMock()
        client.paired=paired
        client.pair_record={}
        client.validate_pairing.return_value=True
        return client

    async def test_valid_existing_identity_does_not_pair_again(self):
        client=self.client(True)
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue((await self.run_repair(client,Path(root)))['ok'])
        client.pair.assert_not_awaited()
        client.close.assert_awaited_once()

    async def test_explicit_repair_preserves_old_record_and_validates(self):
        client=self.client()
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/'phone13.plist').write_bytes(b'previous-record')
            self.assertTrue((await self.run_repair(client,root))['ok'])
            self.assertEqual(next((root/'trust-backups').glob('*.plist')).read_bytes(),b'previous-record')
        client.pair.assert_awaited_once_with(timeout=60,private_key=None)
        client.validate_pairing.assert_awaited_once()
        client.close.assert_awaited_once()

    async def test_unaccepted_pairing_is_not_reported_successful(self):
        client=self.client()
        client.validate_pairing.return_value=False
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                await self.run_repair(client,Path(root))
        client.close.assert_awaited_once()

    async def test_denial_closes_connection_and_does_not_validate(self):
        client=self.client()
        client.pair.side_effect=TimeoutError()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TimeoutError):
                await self.run_repair(client,Path(root))
        client.validate_pairing.assert_not_awaited()
        client.close.assert_awaited_once()

if __name__=='__main__':
    unittest.main()
