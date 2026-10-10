"""Inspect the known Messages target's native action and geometry metadata."""
import asyncio,json,sys
from native_workspace import ROOT
from message_notifications import elements,parse_notification,serialize
from pymobiledevice3.services.accessibilityaudit import deserialize_object
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit

def safe(value):
    if hasattr(value,'_fields'):return safe(value._fields)
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(v) for v in value]
    if isinstance(value,bytes):return {'hex':value.hex()}
    return value if value is None or isinstance(value,(str,int,float,bool)) else str(type(value))

async def main():
    device='00008030-001119CE0A93402E'
    lockdown=await create_using_usbmux(serial=device,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            print(json.dumps({'capabilities':safe(await service.capabilities())},ensure_ascii=True),flush=True)
            items=await elements(service)
            targets=[i for i in items if parse_notification(i.caption,i.platform_identifier,device)]
            for target in targets:
                while not service._event_queue.empty():service._event_queue.get_nowait()
                for name in ('Label','AXFrame','Frame','AXPosition','AXSize','AXActivationPoint'):
                    attribute={'AttributeNameValue_v1':name,'HumanReadableNameValue_v1':name,
                        'ValueTypeValue_v1':2,'PerformsActionValue_v1':False,'SettableValue_v1':False,
                        'DisplayAsTree_v1':False,'IsInternal_v1':False}
                    try:
                        value=await asyncio.wait_for(service._invoke('deviceElement:valueForAttribute:',
                            serialize('AXAuditElement_v1',{'PlatformElementValue_v1':target.element.identifier}),
                            serialize('AXAuditElementAttribute_v1',attribute)),2)
                        print(json.dumps({'attribute':name,'value':safe(deserialize_object(value))},ensure_ascii=True),flush=True)
                        while True:
                            try:
                                event,payload=await asyncio.wait_for(service._event_queue.get(),.25)
                                print(json.dumps({'attribute':name,'event':event,'payload':safe(payload)},ensure_ascii=True),flush=True)
                            except asyncio.TimeoutError:break
                    except Exception as exc:
                        print(json.dumps({'attribute':name,'error':type(exc).__name__}),flush=True)
            output=[{'caption':i.caption,'fields':safe(i._fields)} for i in targets]
            (ROOT/'diagnostics'/'notification-target-attributes.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(output,ensure_ascii=True),flush=True)
    finally:await lockdown.close()

if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
