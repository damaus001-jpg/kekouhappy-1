"""Read-only validation of existing pairing identities; never pairs/unpairs."""
import asyncio
import json
from pathlib import Path

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.pair_records import get_itunes_pairing_record, get_local_pairing_record, get_usbmux_pairing_record
from pymobiledevice3.usbmux import list_devices

DATA = Path(__file__).resolve().parent


async def check(device):
    udid = device.serial
    sources = [('apple-usbmux', await get_usbmux_pairing_record(udid, '127.0.0.1:27015')),
               ('apple-disk', get_itunes_pairing_record(udid)),
               ('project-cache', get_local_pairing_record(udid, DATA))]
    results = []
    for name, record in sources:
        if not record:
            results.append({'source':name, 'record':False})
            continue
        try:
            client = await asyncio.wait_for(create_using_usbmux(serial=udid, connection_type='USB',
                pair_record=record, pairing_records_cache_folder=DATA,
                usbmux_address='127.0.0.1:27015', autopair=False), 12)
            try:
                results.append({'source':name, 'record':True, 'paired':bool(client.paired)})
            finally:
                await client.close()
        except Exception as exc:
            results.append({'source':name,'record':True,'error':type(exc).__name__})
    return {'udid':udid,'sources':results}


async def main():
    devices = await list_devices()
    # Only validate the identities of devices previously missing trust.
    ids = {'00008030-00040DD23E42402E','00008030-00044C540285402E',
           '00008030-000518813442402E','00008030-000A046E2E9B402E',
           '00008030-0011504E1132402E','00008030-001259D42209802E'}
    result = await asyncio.gather(*(check(d) for d in devices if d.serial in ids))
    (DATA/'diagnostics/pair-source-status.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)


asyncio.run(main())
