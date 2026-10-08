"""Read native audit rectangles; does not request screenshots or input."""
import asyncio,json,sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object,SERIALIZABLE_OBJECTS,SerializedObject
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
SERIALIZABLE_OBJECTS['AXAuditNode_v1']=SerializedObject

def safe(v):
    if hasattr(v,'_fields'):return {'type':type(v).__name__,'fields':safe(v._fields)}
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    if isinstance(v,bytes):return {'hex':v.hex()}
    if isinstance(v,(list,tuple)):return [safe(x) for x in v]
    return v if v is None or isinstance(v,(str,int,float,bool)) else repr(v)
async def main():
    ld=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            for sel in ('deviceApiVersion','deviceAuditIssueSupportedKeys','deviceAllSupportedAuditTypes'):
                try:print(json.dumps({'query':sel,'value':safe(deserialize_object(await s._invoke(sel)))}),flush=True)
                except Exception as e:print(json.dumps({'query':sel,'error':str(e)}),flush=True)
            try:
                issues=await asyncio.wait_for(s.run_audit(['testTypeHitRegion']),40)
                data=safe(issues)
                (ROOT/'diagnostics'/'native-hit-regions.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'native_hit_region_issues':data}),flush=True)
            except Exception as e:print(json.dumps({'audit_error':str(e)}),flush=True)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
