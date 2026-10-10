"""Read-only hit test for the visually inspected notification card."""
import asyncio,json,sys
from bpylist2 import archiver
from native_workspace import ROOT
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object

class Point:
    def encode_archive(self,archive):
        archive._archive_obj['NS.special']=1
        archive.encode('NS.pointval','{0.5, 0.70}')
archiver.ARCHIVE_CLASS_MAP[Point]='NSValue'

def safe(value):
    if hasattr(value,'_fields'):return safe(value._fields)
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(v) for v in value]
    if isinstance(value,bytes):return {'hex':value.hex()}
    return value if value is None or isinstance(value,(str,int,float,bool)) else str(type(value))

async def main():
    lockdown=await create_using_usbmux(serial='00008030-001119CE0A93402E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            await service.set_app_monitoring_enabled(True)
            await service.set_monitored_event_type(2)
            response=await asyncio.wait_for(service._invoke('deviceFetchElementAtNormalizedDeviceCoordinate:',Point()),5)
            print(json.dumps({'response':safe(deserialize_object(response))}),flush=True)
            for _ in range(3):
                try:
                    name,args=await asyncio.wait_for(service._event_queue.get(),1)
                    print(json.dumps({'name':name,'payload':safe(deserialize_object(service._extract_event_payload(args)))}),flush=True)
                except asyncio.TimeoutError:break
            await service.set_app_monitoring_enabled(False)
    finally:await lockdown.close()

if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
