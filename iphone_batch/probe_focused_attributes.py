"""Inspect the exact attribute descriptors of focused native elements, without images."""
import asyncio
import json
import sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from native_action import serialize

ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT

def summarize(value):
    if isinstance(value,bytes):return {'bytes':len(value)}
    if isinstance(value,dict):return {k:summarize(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [summarize(v) for v in value[:10]]
    if hasattr(value,'_fields'):return summarize(value._fields)
    return value if isinstance(value,(str,int,float,bool)) or value is None else type(value).__name__

async def main():
    lockdown=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            target=None;iterator=service.iter_elements()
            try:
                async with asyncio.timeout(15):
                    async for item in iterator:
                        if ', Unread, ' in (item.caption or ''):
                            target=item;break
            finally:await iterator.aclose()
            if target is None:
                print(json.dumps({'status':'no_unread_element'}));return
            print(json.dumps({'status':'focused_unread','caption':target.caption,'element_id':target.platform_identifier},ensure_ascii=True),flush=True)
            descriptors=[]
            for section in target._fields.get('InspectorSectionsValue_v1',[]):
                for attribute in section._fields.get('ElementAttributesValue_v1',[]):
                    if attribute._fields.get('AttributeNameValue_v1') in ('Label','Value','Identifier','ElementClassName'):
                        descriptors.append(attribute._fields)
            element=serialize('AXAuditElement_v1',{'PlatformElementValue_v1':target.element.identifier})
            while not service._event_queue.empty():service._event_queue.get_nowait()
            for descriptor in descriptors:
                response=await asyncio.wait_for(service._invoke('deviceElement:valueForAttribute:',element,serialize('AXAuditElementAttribute_v1',descriptor)),timeout=3)
                print(json.dumps({'attribute':descriptor['AttributeNameValue_v1'],'result':summarize(response)},ensure_ascii=True),flush=True)
                try:
                    name,payload=await asyncio.wait_for(service._event_queue.get(),timeout=.6)
                    print(json.dumps({'event':name,'payload':summarize(payload)},ensure_ascii=True),flush=True)
                except asyncio.TimeoutError:pass
            await service.set_app_monitoring_enabled(False)
    finally:await lockdown.close()

if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
