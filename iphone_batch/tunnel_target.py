"""Keep explicitly targeted CLI commands from opening other phones' RSDs."""
import asyncio


def install():
    from pymobiledevice3.cli import cli_common
    from pymobiledevice3.tunneld.api import get_tunneld_device_by_udid
    from pymobiledevice3.exceptions import NoDeviceConnectedError
    original = cli_common._tunneld
    if getattr(original, '_workspace_targeted', False):
        return

    async def targeted(spec=None):
        if spec is None:
            return await original(spec)
        udid, address, bridge = cli_common._parse_tunnel_spec(spec)
        if not udid:
            return await original(spec)
        try:
            service = await asyncio.wait_for(
                get_tunneld_device_by_udid(udid, address, bridge=bridge), 10)
        except IndexError:
            # Upstream indexes an empty list when the one matching RSD failed.
            raise NoDeviceConnectedError() from None
        if service is None:
            raise NoDeviceConnectedError()
        return service

    targeted._workspace_targeted = True
    cli_common._tunneld = targeted
