import asyncio,json,sys
from native_workspace import ROOT,context
from native_ui_scan import scan
from native_conversation import NativeConversation
from probe_history_scroll import swipe
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
async def main():
    phone=NativeConversation();phone.base='http://127.0.0.1:8080'
    ld=await create_using_usbmux(serial='00008030-001119CE0A93402E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            for _ in range(7):await swipe(phone,True)
            pages=[]
            for step in range(3):
                items=await scan(s,limit=3000,seconds=30,settle=.04,start_from_last=False)
                records=[{'caption':i.caption or '', 'platform_identifier':i.platform_identifier} for i in items]
                try:value=context(records)
                except Exception as e:
                    print(json.dumps({'error':str(e),'captions':[r['caption'] for r in records]},ensure_ascii=True),flush=True)
                    return
                value.update(step=step,complete=items.complete)
                pages.append(value)
                print(json.dumps({'step':step,'count':len(value['messages']),'complete':items.complete,'texts':[m['text'] for m in value['messages']]},ensure_ascii=True),flush=True)
                await swipe(phone,False)
            (ROOT/'diagnostics'/'history-from-top.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
