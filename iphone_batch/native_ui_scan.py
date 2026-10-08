"""Bounded native UI scan using caption and identifier to avoid recycled-view early stop."""
import asyncio,json,sys,time
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object,Direction
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
async def scan(s,limit=90,seconds=22):
    await s.set_app_monitoring_enabled(True);await s.set_monitored_event_type()
    while not s._event_queue.empty():s._event_queue.get_nowait()
    await s.move_focus(Direction.First)
    out=[];seen=set();started=time.monotonic()
    while len(out)<limit and time.monotonic()-started<seconds:
        try:name,args=await asyncio.wait_for(s._event_queue.get(),1)
        except asyncio.TimeoutError:await s.move_focus_next();continue
        if name!='hostInspectorCurrentElementChanged:':continue
        data=deserialize_object(s._extract_event_payload(args));items=data if isinstance(data,list) else [data]
        if not items:continue
        i=items[0];key=(i.platform_identifier,i.caption)
        if key in seen:break
        seen.add(key);out.append(i)
        await asyncio.sleep(.15);await s.move_focus_next()
    await s.set_app_monitoring_enabled(False)
    return out
async def main():
    ld=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            print(json.dumps({'captions':[i.caption for i in await scan(s)]}),flush=True)
    finally:await ld.close()
if __name__=='__main__':
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
