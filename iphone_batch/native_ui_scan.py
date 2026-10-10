"""Bounded native UI scan using caption and identifier to avoid recycled-view early stop."""
import asyncio,json,sys,time
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object,Direction
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
class ScanResult(list):
    complete = False
    reason = 'limit'
    elapsed = 0


async def scan(s,limit=90,seconds=22,settle=.15,start_from_last=True):
    await s.set_app_monitoring_enabled(True);await s.set_monitored_event_type()
    await asyncio.sleep(.1)
    while not s._event_queue.empty():s._event_queue.get_nowait()
    # First may produce no event when the inspector is already at First.
    # Move away before restarting at the beginning; never skip its first row.
    if start_from_last:
        await s.move_focus(Direction.Last)
    else:
        await s.move_focus_next()
    # Wait for the Last acknowledgement instead of relying on a fixed delay.
    deadline=time.monotonic()+.8
    while time.monotonic()<deadline:
        try:name,args=await asyncio.wait_for(s._event_queue.get(),max(.01,deadline-time.monotonic()))
        except asyncio.TimeoutError:break
        if name=='hostInspectorCurrentElementChanged:':break
    while not s._event_queue.empty():s._event_queue.get_nowait()
    await s.move_focus(Direction.First)
    out=ScanResult();seen=set();started=time.monotonic();anchor=None;wrapping=False;start_retries=0
    try:
        while len(out)<limit and time.monotonic()-started<seconds:
            try:name,args=await asyncio.wait_for(s._event_queue.get(),min(2,max(.01,seconds-(time.monotonic()-started))))
            except asyncio.TimeoutError:
                if not out and start_retries<2:
                    start_retries+=1
                    await s.move_focus(Direction.First);continue
                # An unacknowledged Next must never be followed by another Next:
                # a delayed event could otherwise make us skip a contact.
                out.reason='event_timeout';break
            if name!='hostInspectorCurrentElementChanged:':continue
            data=deserialize_object(s._extract_event_payload(args));items=data if isinstance(data,list) else [data]
            if not items:continue
            i=items[0];key=(i.platform_identifier,i.caption)
            if wrapping:
                if key==anchor:continue  # Duplicate acknowledgement, not another step.
                out.complete=len(out)>1 and key==(out[1].platform_identifier,out[1].caption)
                out.reason='cycle_verified' if out.complete else 'unstable_cycle'
                break
            if key in seen:
                if out and key==(out[-1].platform_identifier,out[-1].caption):
                    continue  # Keep waiting for the already-requested Next.
                if key==anchor and len(out)>1:
                    wrapping=True
                    await s.move_focus_next();continue
                out.reason='repeated_element';break
            if anchor is None:anchor=key
            seen.add(key);out.append(i)
            if settle:await asyncio.sleep(settle)
            await s.move_focus_next()
        else:
            out.reason='limit' if len(out)>=limit else 'time_limit'
    finally:
        out.elapsed=round(time.monotonic()-started,3)
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
