import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native_workspace import ROOT,read,validate_snapshot
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
async def main():
    ld=await create_using_usbmux(serial='00008030-001119CE0A93402E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(ld) as s:
            current=await read(s)
            record_path=max((ROOT/'workspace/replies').glob('*.json'),key=lambda p:p.stat().st_mtime)
            record=json.loads(record_path.read_text(encoding='utf-8'))
            captions=[r['caption'] for r in current['raw_elements']]
            result={'phone_number':current['phone_number'],'expected_number':record['phone_number'],'expected_text':record['english'],'send_button_present':any(c.startswith('Send, Button') for c in captions),'composer_elements':[c for c in captions if c.startswith(('Message','Send,','Dictate','Audio','Keyboard'))],'outgoing_matches':sum(m['side']=='outgoing' and m['text']==record['english'] for m in current['messages'])}
            try:validate_snapshot(current,record);result['snapshot_valid']=True
            except Exception as e:result['snapshot_error']=str(e)
            print(json.dumps(result,ensure_ascii=True))
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
