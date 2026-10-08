"""Paced native list read; no screenshots, tapping or text-based message deduplication."""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit

ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
async def main(args):
    samples=[]
    for number in range(args.samples):
        lockdown=await create_using_usbmux(serial=args.udid,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
        records=[];reason='focus_cycle'
        try:
            async with AccessibilityAudit(lockdown) as service:
                await service.set_show_visuals(False)
                iterator=service.iter_elements()
                try:
                    async with asyncio.timeout(35):
                        async for item in iterator:
                            records.append(item.to_dict())
                            if len(records)>=60:
                                reason='element_limit';break
                            await asyncio.sleep(args.settle_ms/1000)
                except asyncio.TimeoutError:
                    reason='timeout'
                finally:
                    await iterator.aclose();await service.set_app_monitoring_enabled(False)
        finally:await lockdown.close()
        samples.append({'records':records,'stop_reason':reason})
        print(json.dumps({'sample':number+1,'settle_ms':args.settle_ms,'elements':len(records),'unread_rows':sum(', Unread, ' in (r.get('caption') or '') for r in records),'stop_reason':reason}),flush=True)
    path=ROOT/'diagnostics'/('unread-paced-'+args.udid[-8:]+'-'+str(args.settle_ms)+'.json')
    path.write_text(json.dumps({'created':datetime.now().isoformat(),'device':args.udid,'settle_ms':args.settle_ms,'samples':samples},ensure_ascii=False,indent=2),encoding='utf-8')
    counts=[sum(', Unread, ' in (r.get('caption') or '') for r in sample['records']) for sample in samples]
    print(json.dumps({'counts':counts,'same_caption_sequence':all([r.get('caption') for r in sample['records']]==[r.get('caption') for r in samples[0]['records']] for sample in samples),'record':str(path)}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--udid',required=True);parser.add_argument('--settle-ms',type=int,default=500);parser.add_argument('--samples',type=int,default=3);args=parser.parse_args()
    if not 0<=args.settle_ms<=2000 or not 1<=args.samples<=5:parser.error('Invalid pacing limits')
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
