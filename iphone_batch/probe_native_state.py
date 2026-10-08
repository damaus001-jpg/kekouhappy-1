import asyncio
import json
import sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
async def main():
    lockdown=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            result=await asyncio.wait_for(service._invoke('deviceCurrentState'),timeout=4)
            print(json.dumps({'state_type':type(result).__name__,'state':result},default=lambda v:{'type':type(v).__name__},ensure_ascii=True),flush=True)
            for _ in range(6):
                try:
                    name,args=await asyncio.wait_for(service._event_queue.get(),timeout=.5)
                    print(json.dumps({'event':name,'payload':args},default=lambda v:{'type':type(v).__name__},ensure_ascii=True),flush=True)
                except asyncio.TimeoutError:break
    finally:await lockdown.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
