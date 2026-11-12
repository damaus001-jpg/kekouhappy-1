import asyncio
import json
from pathlib import Path
import sys

DATA=Path(__file__).resolve().parent
sys.path.insert(0,str(DATA.parent))
from pairing_patch import install
install()
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.mobile_image_mounter import MobileImageMounterService

DEVICES={'04':'00008030-001E301922D8402E','07':'00008030-001838463A78802E',
         '14':'00008030-000315A00EB9402E','17':'00008030-001259D42209802E',
         '18':'00008030-0011504E1132402E'}


async def check(number,udid):
    row={'number':number,'udid':udid}
    try:
        ld=await create_using_usbmux(serial=udid,connection_type='USB',autopair=False,
            pairing_records_cache_folder=DATA,usbmux_address='127.0.0.1:27015')
        try:
            row['version']=ld.product_version
            async with MobileImageMounterService(ld) as service:
                row['developer_mode']=await service.query_developer_mode_status()
                images=await service.copy_devices()
                row['mounted_images']=[image.get('ImageType',image.get('DiskImageType','unknown')) for image in images]
        finally:
            await ld.close()
    except Exception as exc:
        row['error']=type(exc).__name__+': '+str(exc)
    print(json.dumps(row,ensure_ascii=True),flush=True)
    return row


async def main():
    rows=await asyncio.gather(*(check(n,u) for n,u in DEVICES.items()))
    (DATA/'diagnostics/pending-developer-state.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')


asyncio.run(main())
