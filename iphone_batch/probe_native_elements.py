"""Read native accessibility element attributes without screenshots or coordinate guesses."""
import asyncio
import json
import sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit, deserialize_object

ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT

def passthrough(value):return {'ObjectType':'passthrough','Value':value}
def element_payload(identifier):
    return {'ObjectType':'AXAuditElement_v1','Value':passthrough({'PlatformElementValue_v1':passthrough(identifier)})}
def attribute_payload(name):
    return {'ObjectType':'AXAuditElementAttribute_v1','Value':passthrough({'AttributeNameValue_v1':passthrough(name)})}
def safe(value):
    if isinstance(value,bytes):return {'bytes':len(value)}
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(v) for v in value[:30]]
    if hasattr(value,'_fields'):return safe(value._fields)
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    return type(value).__name__

async def main():
    lockdown=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            targets={};iterator=service.iter_elements()
            try:
                async with asyncio.timeout(15):
                    async for item in iterator:
                        caption=item.caption or ''
                        if caption.startswith('Message, ') or caption.startswith('Send, Button'):
                            targets['input' if caption.startswith('Message, ') else 'send']=item
                            if len(targets)==2:break
            finally:
                await iterator.aclose();await service.set_app_monitoring_enabled(False)
            for label,item in targets.items():
                print(json.dumps({'element':label,'caption':item.caption,'fields':list(item._fields),'sections':safe(item._fields.get('InspectorSectionsValue_v1'))},ensure_ascii=True),flush=True)
                serialized=element_payload(bytes.fromhex(item.platform_identifier))
                # Confirm local round-trip rather than trusting malformed upstream element payloads.
                assert deserialize_object(serialized).identifier==item.element.identifier
                for name in ('AXFrame','AXValue'):
                    try:
                        result=await asyncio.wait_for(service._invoke('deviceElement:valueForAttribute:',serialized,attribute_payload(name)),timeout=3)
                        print(json.dumps({'element':label,'attribute':name,'result':safe(result)},ensure_ascii=True),flush=True)
                    except Exception as error:
                        print(json.dumps({'element':label,'attribute':name,'error':type(error).__name__}),flush=True)
    finally:await lockdown.close()

if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())

