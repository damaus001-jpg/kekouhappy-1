import asyncio,json,sys
from native_workspace import ROOT,raw_page,context
from native_conversation import NativeConversation
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
async def swipe(phone,toward_top):
    start,end=(.30,.78) if toward_top else (.78,.30)
    try:
        for i in range(19):
            phone.request(phone.base,'/touch',{'type':'contact','x':32768,'y':round((start+(end-start)*i/18)*65535)})
            await asyncio.sleep(.025)
    finally:phone.request(phone.base,'/touch',{'type':'release','x':32768,'y':round(end*65535)})
    await asyncio.sleep(.6)
async def main():
    phone=NativeConversation();phone.base='http://127.0.0.1:8080'
    ld=await create_using_usbmux(serial='00008030-001119CE0A93402E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    pages=[]
    try:
        async with AccessibilityAudit(ld) as s:
            for n in range(9):
                if n:await swipe(phone,n<5)
                rows=await raw_page(s,full=True)
                try:value=context(rows);summary={'count':len(value['messages']),'texts':[m['text'] for m in value['messages']]}
                except Exception as e:summary={'error':str(e)}
                summary.update(step=n,complete=rows.complete,captions=[r['caption'] for r in rows]);pages.append(summary)
                print(json.dumps(summary,ensure_ascii=True),flush=True)
    finally:
        (ROOT/'diagnostics'/'history-scroll-probe.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
        await ld.close()
if __name__=='__main__':
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

