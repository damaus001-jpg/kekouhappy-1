import unittest
from unittest.mock import AsyncMock, patch
from pymobiledevice3.cli import cli_common
from pymobiledevice3.exceptions import NoDeviceConnectedError
from tunnel_target import install


class TargetedTunnelTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_target_never_enumerates_other_connections(self):
        original = AsyncMock()
        original._workspace_targeted = False
        selected = object()
        with patch.object(cli_common, '_tunneld', original), patch(
                'pymobiledevice3.tunneld.api.get_tunneld_device_by_udid',
                AsyncMock(return_value=selected)) as lookup:
            install()
            self.assertIs(await cli_common._tunneld('phone'), selected)
            lookup.assert_awaited_once_with('phone', ('127.0.0.1', 49151), bridge=None)
            original.assert_not_awaited()

    async def test_missing_target_never_falls_back_to_another_phone(self):
        for result in (None, IndexError()):
            original = AsyncMock()
            original._workspace_targeted = False
            lookup = AsyncMock(side_effect=result) if isinstance(result, Exception) else AsyncMock(return_value=result)
            with patch.object(cli_common, '_tunneld', original), patch(
                    'pymobiledevice3.tunneld.api.get_tunneld_device_by_udid', lookup):
                install()
                with self.assertRaises(NoDeviceConnectedError):
                    await cli_common._tunneld('phone')
                original.assert_not_awaited()

    async def test_explicit_bridge_option_is_preserved(self):
        original = AsyncMock()
        original._workspace_targeted = False
        with patch.object(cli_common, '_tunneld', original), patch(
                'pymobiledevice3.tunneld.api.get_tunneld_device_by_udid', AsyncMock()) as lookup:
            install()
            await cli_common._tunneld('phone@127.0.0.1:49151')
            lookup.assert_awaited_once_with('phone', ('127.0.0.1', 49151), bridge=True)
