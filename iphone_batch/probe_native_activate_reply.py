import asyncio,json,sys
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from native_action import serialize
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
async def main():
    ld=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            it=s.iter_elements();target=None
            try:
                async with asyncio.timeout(18):
                    async for i in it:
                        if ', Unread, ' in (i.caption or ''):target=i;break
            finally:await it.aclose()
            if target is None:print('No unread target');return
            print(json.dumps({'target':target.caption}),flush=True)
            el=serialize('AXAuditElement_v1',{'PlatformElementValue_v1':target.element.identifier})
            attrs=[a._fields for sec in target._fields.get('InspectorSectionsValue_v1',[]) for a in sec._fields.get('ElementAttributesValue_v1',[])]
            print(json.dumps({'attributes':attrs},default=lambda x: type(x).__name__),flush=True)
            action=next(a for a in attrs if a.get('AttributeNameValue_v1')=='AXAction-2010')
            try:
                result=await asyncio.wait_for(s._invoke('deviceElement:performAction:withValue:',el,serialize('AXAuditElementAttribute_v1',action),0),5)
                print(json.dumps({'activation_reply':result},default=str),flush=True)
            except Exception as e:print(json.dumps({'activation_error':str(e)}),flush=True)
            await asyncio.sleep(1)
            it=s.iter_elements();captions=[]
            try:
                async with asyncio.timeout(18):
                    async for i in it:captions.append(i.caption)
            finally:await it.aclose()
            print(json.dumps({'after':captions}),flush=True)
            await s.set_app_monitoring_enabled(False)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
