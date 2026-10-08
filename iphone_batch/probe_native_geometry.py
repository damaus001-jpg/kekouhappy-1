"""Query native geometry and hierarchy. Never captures screen images or sends touch."""
import asyncio,json,sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object,SERIALIZABLE_OBJECTS,SerializedObject
from native_action import serialize
SERIALIZABLE_OBJECTS['AXAuditNode_v1']=SerializedObject
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT

def safe(v):
    if isinstance(v,bytes):return {'hex':v.hex()}
    if hasattr(v,'_fields'):return {'type':type(v).__name__,'fields':safe(v._fields)}
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [safe(x) for x in v]
    return v if v is None or isinstance(v,(str,int,float,bool)) else repr(v)
async def main():
    ld=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    results=[]
    try:
        async with AccessibilityAudit(ld) as s:
            print(json.dumps({'capabilities':safe(await s.capabilities())}),flush=True)
            it=s.iter_elements();target=None
            try:
                async with asyncio.timeout(18):
                    async for i in it:
                        if ', Unread, ' in (i.caption or ''):target=i;break
            finally:await it.aclose()
            if target is None:print('No unread target');return
            results.append({'focus_raw':safe(target)})
            print(json.dumps({'target':target.caption,'fields':list(target._fields)}),flush=True)
            el=serialize('AXAuditElement_v1',{'PlatformElementValue_v1':target.element.identifier})
            attrs=[a._fields for sec in target._fields.get('InspectorSectionsValue_v1',[]) for a in sec._fields.get('ElementAttributesValue_v1',[])]
            base=next(a for a in attrs if a.get('AttributeNameValue_v1')=='Label')
            descriptors=[a for a in attrs if not a.get('PerformsActionValue_v1')]
            for name in ('Frame','AXFrame','Rect','Position','Size','accessibilityFrame','_AXFrameAttribute','_AXBoundsAttribute','_AXElementRectAttribute','ActivationPoint'):
                descriptors.append({**base,'AttributeNameValue_v1':name,'HumanReadableNameValue_v1':name})
            for a in descriptors:
                try:
                    v=await asyncio.wait_for(s._invoke('deviceElement:valueForAttribute:',el,serialize('AXAuditElementAttribute_v1',a)),3)
                    out={'attribute':a['AttributeNameValue_v1'],'result':safe(deserialize_object(v))}
                except Exception as e:out={'attribute':a['AttributeNameValue_v1'],'error':str(e)[:500]}
                results.append(out);print(json.dumps(out),flush=True)
            while not s._event_queue.empty():
                name,args=s._event_queue.get_nowait();results.append({'event':name,'payload':safe(args)})
            await s.set_app_monitoring_enabled(False)
    finally:
        (ROOT/'diagnostics'/'native-geometry.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
