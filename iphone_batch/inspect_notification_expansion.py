"""Tap the known incoming test notification once and inspect its expanded controls."""
import asyncio
import json
import sys
from native_conversation import NativeConversation
from native_workspace import ROOT
from message_notifications import enter_center, elements, parse_notification
from notification_touch import tap_notification, frame
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit


async def main():
    device='00008030-001119CE0A93402E'
    phone=NativeConversation()
    phone.base='http://127.0.0.1:8080'
    phone.request('http://127.0.0.1:8070','/api/notification-policy',{'device':device,'protected':True})
    try:
        await asyncio.sleep(3)
        phone.request('http://127.0.0.1:8070','/api/select',{'udid':device})
        lockdown=await create_using_usbmux(serial=device,connection_type='USB',
            usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
        try:
            async with AccessibilityAudit(lockdown) as service:
                current,_=await enter_center(service,phone)
                matches=[row for item in current
                    if (row:=parse_notification(item.caption,item.platform_identifier,device))
                    and row['phone_number']=='+19562154700' and row['preview']=='good morning']
                if len(matches)!=1:raise ValueError('Test notification not unique; did not tap')
                await tap_notification(service,phone,device,matches[0])
                await asyncio.sleep(.5)
                output=ROOT/'diagnostics'/'notification-expanded.png'
                await asyncio.to_thread(frame,phone,output)
                current=await elements(service)
                print(json.dumps({'elements':[{'caption':i.caption,'id':i.platform_identifier} for i in current]},ensure_ascii=True),flush=True)
                print(str(output),flush=True)
        finally:await lockdown.close()
    finally:
        phone.request('http://127.0.0.1:8070','/api/notification-policy',{'device':device,'protected':False})


if __name__=='__main__':
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
