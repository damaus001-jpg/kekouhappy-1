"""Use this project's trusted pair records before stale Apple service records."""
from pathlib import Path
import plistlib


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
