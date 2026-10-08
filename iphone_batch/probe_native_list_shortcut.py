"""Test keyboard navigation directly from unread list; no images, text input or send."""
import asyncio,json,sys
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from native_conversation import NativeConversation,ROOT,DEVICE
from native_ui_scan import scan
async def main():
    ld=await create_using_usbmux(serial=DEVICE,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    p=NativeConversation()
    try:
        async with AccessibilityAudit(ld) as s:
            before=[i.caption or '' for i in await scan(s)]
            p.select()
            if any(c.startswith('New Message, Show Conversation Details, Button') for c in before):
                if not any(c=='To:, ralston' for c in before) or any(c.startswith('Send, Button') for c in before):raise RuntimeError('Uncommitted recipient search not confirmed')
                await p.keys([0x29]);await p.keys([]);await asyncio.sleep(.5)
                before=[i.caption or '' for i in await scan(s)]
            print(json.dumps({'list_before':before}),flush=True)
            if 'Unread, Header' not in before or any(', Show Conversation Details, Button' in c for c in before):raise RuntimeError('Unread list not confirmed')
            await p.chord(0x51);await asyncio.sleep(.6)
            after=[i.caption or '' for i in await scan(s)]
            print(json.dumps({'after_command_down':after,'send_clicked':False}),flush=True)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
