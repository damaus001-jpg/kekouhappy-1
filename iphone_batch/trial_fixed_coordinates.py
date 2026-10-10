import asyncio,json,sys
from native_workspace import ROOT,read,composer_is_empty
from native_conversation import NativeConversation
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
async def main():
    phone=NativeConversation();phone.base='http://127.0.0.1:8080';text='Coordinate test.'
    ld=await create_using_usbmux(serial='00008030-001119CE0A93402E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            current=await read(s);captions=[r['caption'] for r in current['raw_elements']]
            if not composer_is_empty(captions):raise ValueError('Existing draft preserved; no input')
            key=current['phone_number'];point={'x':round(.5*65535),'y':round((1694/1808)*65535)}
            try:
                phone.request(phone.base,'/touch',{'type':'contact',**point});await asyncio.sleep(.08)
            finally:phone.request(phone.base,'/touch',{'type':'release',**point})
            await asyncio.sleep(.5);await phone.paste(text);await asyncio.sleep(.5)
            prepared=await read(s);captions=[r['caption'] for r in prepared['raw_elements']]
            result={'phone_number':prepared['phone_number'],'recipient_unchanged':key==prepared['phone_number'],'text_verified':'Message, '+text in captions,'send_button_present':any(c.startswith('Send, Button') for c in captions),'composer_elements':[c for c in captions if c.startswith(('Message','Send,'))],'send_clicked':False}
            (ROOT/'diagnostics'/'fixed-coordinate-trial.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=True))
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
