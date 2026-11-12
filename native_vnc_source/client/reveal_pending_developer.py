"""Show the developer-mode toggle; never enable or reboot a phone."""
import asyncio
import json
from pathlib import Path
import sys

DATA=Path(__file__).resolve().parent
sys.path.insert(0,str(DATA.parent))
from pairing_patch import install
install()
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.amfi import AmfiService


async def show(number,udid):
    ld=await create_using_usbmux(serial=udid,connection_type='USB',autopair=False,
        pairing_records_cache_folder=DATA,usbmux_address='127.0.0.1:27015')
    try:
        await AmfiService(ld).reveal_developer_mode_option_in_ui()
        print(json.dumps({'number':number,'developer_mode_option_revealed':True,
            'device_name':ld.all_values.get('DeviceName'),
            'serial_suffix':str(ld.all_values.get('SerialNumber',''))[-4:]},ensure_ascii=True),flush=True)
    finally:
        await ld.close()


async def main():
    await asyncio.gather(show('17','00008030-001259D42209802E'),show('18','00008030-0011504E1132402E'))


asyncio.run(main())
