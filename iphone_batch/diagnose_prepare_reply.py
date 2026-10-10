import asyncio,json,sys
from pathlib import Path
from native_workspace import ROOT,read,raw_page,composer_is_empty,validate_snapshot
from native_conversation import NativeConversation,phone_key
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
async def main():
    record=json.loads((ROOT/'workspace/replies/eb3daf376c6b4c6e8a517657cc7c1c5b.json').read_text(encoding='utf-8'))
    phone=NativeConversation();phone.base='http://127.0.0.1:8080'
    ld=await create_using_usbmux(serial=record['device'],connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            current=await read(s)
            if current['phone_number']!=record['phone_number'] or not composer_is_empty([r['caption'] for r in current['raw_elements']]):raise ValueError('Original recipient or empty composer not confirmed')
            validate_snapshot(current,record)
            await phone.chord(0x11);await asyncio.sleep(.4)
            captions=[r['caption'] for r in await raw_page(s)]
            if 'To:' not in captions or 'Message' not in captions:raise ValueError('Empty recipient entry not confirmed')
            await phone.paste(record['phone_number']);await asyncio.sleep(.4)
            captions=[r['caption'] for r in await raw_page(s)]
            if not any(c.startswith('To:, ') and phone_key(c[5:])==record['phone_number'] for c in captions):raise ValueError('Number entry not confirmed')
            await phone.keys([0x28]);await phone.keys([]);await asyncio.sleep(.6)
            current=await read(s)
            if current['phone_number']!=record['phone_number']:raise ValueError('Reopened recipient mismatch')
            validate_snapshot(current,record)
            await phone.keys([0x2B]);await phone.keys([])
            await phone.paste(record['english']);await asyncio.sleep(.5)
            prepared=await read(s)
            captions=[r['caption'] for r in prepared['raw_elements']]
            print(json.dumps({'phone_number':prepared['phone_number'],'composer_elements':[c for c in captions if c.startswith(('Message','Send,','To:'))],'expected_text':record['english'],'send_clicked':False},ensure_ascii=True))
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
