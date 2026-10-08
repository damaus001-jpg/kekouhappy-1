"""Paste full contact name into confirmed empty recipient field; no selection or send."""
import asyncio,json,sys
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from native_conversation import NativeConversation,ROOT,DEVICE
from native_ui_scan import scan
FULL='Ralston \u7f57\u5c14\u65af\u987f \u5185\u5e03\u62c9\u65af\u52a0\u5ddeNE'
async def main():
    ld=await create_using_usbmux(serial=DEVICE,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    p=NativeConversation()
    try:
        async with AccessibilityAudit(ld) as s:
            before=[i.caption or '' for i in await scan(s)]
            if 'To:' not in before or 'Message' not in before or not any(c.startswith('New Message, Show Conversation Details, Button') for c in before):raise RuntimeError('Empty recipient entry not confirmed')
            p.select();p.request(p.base,'/clipboard',{'text':FULL});await p.chord(0x19);await asyncio.sleep(.7)
            after=[i.caption or '' for i in await scan(s)]
            rows=[c for c in after if c.startswith(FULL+', ') and ('iMessage, Button' in c or 'Text Message, Button' in c)]
            entered=[c for c in after if c.startswith('To:')]
            print(json.dumps({'full_name':FULL,'recipient_field':entered,'full_name_verified':any(FULL in c for c in entered),'matching_numbers':rows,'match_count':len(rows),'send_clicked':False}),flush=True)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
