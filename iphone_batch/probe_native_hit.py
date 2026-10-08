"""Probe native element hit testing; no screenshots or HID input."""
import asyncio
import json
import sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT

from bpylist2 import archiver
class NativePoint:
    def __init__(self,x,y):self.x=x;self.y=y
    def encode_archive(self,archive):
        archive._archive_obj['NS.special']=1
        archive.encode('NS.pointval','{'+str(self.x)+', '+str(self.y)+'}')
archiver.ARCHIVE_CLASS_MAP[NativePoint]='NSValue'

def passthrough(value):return {'ObjectType':'passthrough','Value':value}
def safe(value):
    if isinstance(value,bytes):return {'bytes':len(value)}
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(v) for v in value[:10]]
    if hasattr(value,'_fields'):return safe(value._fields)
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    return type(value).__name__

async def main():
    lockdown=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            await service.set_show_visuals(False);await service.set_app_monitoring_enabled(True);await service.set_monitored_event_type()
            for selector,args in [('deviceInspectorEnable:',(True,)),('deviceDidGetTargeted',()),('deviceInspectorSupportedEventTypes',()),('deviceCurrentState',()),('deviceRunningApplications',()),('deviceAccessibilitySettings',())]:
                try:
                    value=await asyncio.wait_for(service._invoke(selector,*args),timeout=3)
                    print(json.dumps({'setup':selector,'result':safe(value)},ensure_ascii=True),flush=True)
                except Exception as error:print(json.dumps({'setup':selector,'error':str(error)[:800]}),flush=True)
            while not service._event_queue.empty():service._event_queue.get_nowait()
            await service.set_monitored_event_type(2)
            formats=[('native_point',NativePoint(.5,.3))]
            for name,point in formats:
                try:
                    result=await asyncio.wait_for(service._invoke('deviceFetchElementAtNormalizedDeviceCoordinate:',point),timeout=3)
                    print(json.dumps({'format':name,'result':safe(result)},ensure_ascii=True),flush=True)
                    for _ in range(4):
                        try:
                            event,payload=await asyncio.wait_for(service._event_queue.get(),timeout=1.2)
                            print(json.dumps({'format':name,'event':event,'payload':safe(payload)},ensure_ascii=True),flush=True)
                        except asyncio.TimeoutError:break
                except Exception as error:print(json.dumps({'format':name,'error':type(error).__name__,'details':str(error)[:1500]}),flush=True)
            await service.set_app_monitoring_enabled(False)
    finally:await lockdown.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())



