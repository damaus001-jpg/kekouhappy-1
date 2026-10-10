import asyncio,json,sys
from native_workspace import ROOT,read
from native_conversation import NativeConversation
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
async def main():
    record=json.loads((ROOT/'workspace/replies/eb3daf376c6b4c6e8a517657cc7c1c5b.json').read_text(encoding='utf-8'))
    phone=NativeConversation();phone.base='http://127.0.0.1:8080'
    ld=await create_using_usbmux(serial=record['device'],connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            current=await read(s)
            captions=[r['caption'] for r in current['raw_elements']]
            if current['phone_number']!=record['phone_number'] or 'Message, '+record['english'] not in captions:raise ValueError('Diagnostic draft changed; preserved')
            await phone.chord(0x04)
            await phone.keys([0x2A]);await phone.keys([]);await asyncio.sleep(.5)
            current=await read(s)
            captions=[r['caption'] for r in current['raw_elements']]
            print(json.dumps({'phone_number':current['phone_number'],'composer_elements':[c for c in captions if c.startswith(('Message','Send,'))],'send_clicked':False},ensure_ascii=True))
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
