"""Use this project's trusted pair records before stale Apple service records."""
from pathlib import Path
import plistlib


class PhoneTrustRequired(RuntimeError):
    def __init__(self):
        super().__init__('手机未接受当前 USB 配对，无法读取短信。请解锁手机，在设备卡片右键选择“重新连接此设备”，若手机弹出信任提示请确认。')


async def open_paired_usb(device, cache):
    """Open an existing, device-validated session for this phone only."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.pair_records import get_itunes_pairing_record, get_usbmux_pairing_record

    install()
    address = '127.0.0.1:27015'
    options = dict(serial=device, connection_type='USB', autopair=False,
                   pairing_records_cache_folder=cache, usbmux_address=address)
    client = await create_using_usbmux(**options)
    if client.paired:
        return client
    tried = [client.pair_record]
    await client.close()
    # A stale project record can hide the current Apple record. Ask only the
    # official active stores for this UDID, and let the phone validate each.
    for source in ('usbmux', 'itunes'):
        record = (await get_usbmux_pairing_record(device, address) if source == 'usbmux'
                  else get_itunes_pairing_record(device))
        if not record or record in tried:
            continue
        tried.append(record)
        client = await create_using_usbmux(pair_record=record, **options)
        if client.paired:
            return client
        await client.close()
    raise PhoneTrustRequired()


def prevent_automatic_pairing():
    """Ordinary CLI reconnection must not create a new host identity/dialog.

    Explicit `lockdown pair` still calls pair() itself after connecting with
    autopair=False. This policy applies only to this project's CLI child.
    """
    from pymobiledevice3 import lockdown
    from pymobiledevice3.exceptions import NotPairedError
    original = lockdown.LockdownClient._handle_autopair
    if getattr(original, '_project_existing_only', False) is True:
        return

    async def existing_only(self, autopair, timeout, private_key=None):
        await original(self, False, timeout, private_key=private_key)
        if autopair and not self.paired:
            raise NotPairedError('现有配对身份未通过；后台不会重新发起信任配对')

    existing_only._project_existing_only = True
    lockdown.LockdownClient._handle_autopair = existing_only


def install():
    from pymobiledevice3 import lockdown
    from pymobiledevice3.pair_records import get_local_pairing_record
    if getattr(lockdown.get_preferred_pair_record, '_project_pairing', False):
        return
    original = lockdown.get_preferred_pair_record

    async def preferred(identifier, pairing_records_cache_folder, usbmux_address=None):
        # Lockdown still validates the record with the phone before using it.
        if Path(pairing_records_cache_folder).resolve() == (Path(__file__).resolve().parent/'.device-data').resolve():
            try:
                record = get_local_pairing_record(identifier, pairing_records_cache_folder)
                if isinstance(record, dict) and all(record.get(key) for key in ('HostID', 'HostPrivateKey', 'HostCertificate', 'SystemBUID')):
                    return record
            except (OSError, ValueError, plistlib.InvalidFileException):
                pass
        return await original(identifier, pairing_records_cache_folder, usbmux_address)

    preferred._project_pairing = True
    lockdown.get_preferred_pair_record = preferred
