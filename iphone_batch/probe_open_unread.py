import asyncio
import json
import sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit

ROOT = Path(__file__).resolve().parent
common._HOMEFOLDER = ROOT / '.device-data'

async def main():
    lockdown = await create_using_usbmux(serial='00008030-001C481A3C32802E', connection_type='USB', usbmux_address='127.0.0.1:27015', pairing_records_cache_folder=common._HOMEFOLDER, autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            await service.set_show_visuals(False)
            target = None
            iterator = service.iter_elements()
            try:
                async with asyncio.timeout(20):
                    async for item in iterator:
                        if ', Unread, ' in (item.caption or ''):
                            target = item
                            break
            finally:
                await iterator.aclose()
                await service.set_app_monitoring_enabled(False)
            if target is None:
                print(json.dumps({'status':'no_unread_found_in_scan'}))
                return
            record = target.to_dict()
            path = ROOT / '.device-data' / 'diagnostics' / 'open-unread-target-3C32802E.json'
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            await service.perform_press(bytes.fromhex(record['platform_identifier']))
            print(json.dumps({'status':'activation_requested','target_saved':str(path)}))
    finally:
        await lockdown.close()

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
