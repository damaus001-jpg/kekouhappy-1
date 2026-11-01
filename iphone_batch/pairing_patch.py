"""Use this project's trusted pair records before stale Apple service records."""
from pathlib import Path
import plistlib


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
