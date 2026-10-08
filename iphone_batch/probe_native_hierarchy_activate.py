"""Activate native hierarchy targets and verify conversation header. No image access."""
import asyncio,json,sys,argparse
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object,SERIALIZABLE_OBJECTS,SerializedObject
from native_action import serialize
SERIALIZABLE_OBJECTS['AXAuditNode_v1']=SerializedObject
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT

def nodes(node):
    f=getattr(node,'_fields',{})
    if 'AuditElementValue_v1' in f:yield f['AuditElementValue_v1']
    for child in f.get('ChildrenValue_v1',[]):yield from nodes(child)
async def captions(s):
    it=s.iter_elements();out=[]
    try:
        async with asyncio.timeout(20):
            async for i in it:out.append(i.caption)
    finally:await it.aclose()
    return out
async def main():
    ld=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            it=s.iter_elements();target=None
            try:
                async with asyncio.timeout(18):
                    async for i in it:
                        if ', Unread, ' in (i.caption or '') and i.caption.startswith('Ralston '):target=i;break
            finally:await it.aclose()
            if target is None:print('Requested unread contact not found');return
            attrs=[a._fields for sec in target._fields.get('InspectorSectionsValue_v1',[]) for a in sec._fields.get('ElementAttributesValue_v1',[])]
            hierarchy=next(a for a in attrs if a.get('AttributeNameValue_v1')=='_AXHierarchyElementsAttribute')
            action=next(a for a in attrs if a.get('AttributeNameValue_v1')=='AXAction-2010')
            payload=lambda e:serialize('AXAuditElement_v1',{'PlatformElementValue_v1':e.identifier})
            h=deserialize_object(await s._invoke('deviceElement:valueForAttribute:',payload(target.element),serialize('AXAuditElementAttribute_v1',hierarchy)))
            targets=list(nodes(h));print(json.dumps({'contact':target.caption,'target_ids':[e.identifier.hex() for e in targets]}),flush=True)
            for e in reversed(targets):
                try:
                    await s._invoke('deviceInspectorFocusOnElement:',payload(e))
                    await asyncio.sleep(.4)
                    reply=await s._invoke('deviceElement:performAction:withValue:',payload(e),serialize('AXAuditElementAttribute_v1',action),0)
                    print(json.dumps({'activated_id':e.identifier.hex(),'reply':reply},default=str),flush=True)
                except Exception as ex:print(json.dumps({'error':str(ex)}),flush=True)
                await asyncio.sleep(.8)
                out=await captions(s)
                print(json.dumps({'after':out}),flush=True)
                if any(', Show Conversation Details, Button' in (c or '') for c in out):
                    print('Conversation opened; stopping without sending.');break
            await s.set_app_monitoring_enabled(False)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
