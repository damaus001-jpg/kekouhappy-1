"""Activate freshly read native UI elements; never uses images or coordinates."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object

ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT

def passthrough(value):return {'ObjectType':'passthrough','Value':value}
def serialize(kind,fields):
    return {'ObjectType':kind,'Value':passthrough({k:passthrough(v) for k,v in fields.items()})}

async def scan(service):
    items=[];iterator=service.iter_elements()
    try:
        async with asyncio.timeout(18):
            async for item in iterator:
                items.append(item)
                if len(items)>=120:break
    finally:
        await iterator.aclose();await service.set_app_monitoring_enabled(False)
    return items

async def main(args):
    lockdown=await create_using_usbmux(serial=args.udid,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            items=await scan(service)
            if args.role=='back':targets=[i for i in items if i.caption=='Back, Button']
            elif args.role=='input':targets=[i for i in items if (i.caption or '').startswith('Message, ')]
            elif args.role=='unread':targets=[i for i in items if ', Unread, ' in (i.caption or '') and (not args.contact or i.caption.startswith(args.contact+', '))]
            elif args.role=='send':
                contacts={i.caption.split(', Show Conversation Details, Button')[0] for i in items if ', Show Conversation Details, Button' in (i.caption or '')}
                if contacts!={args.contact} or not args.text or not any(i.caption=='Message, '+args.text for i in items):
                    raise ValueError('联系人或输入框正文未确认，禁止发送')
                targets=[i for i in items if (i.caption or '').startswith('Send, Button')]
            if args.role=='unread' and not args.contact and targets:targets=targets[:1]
            if len(targets)!=1:raise ValueError('目标元素不唯一或未返回')
            item=targets[0];identifier=item.element.identifier
            element=serialize('AXAuditElement_v1',{'PlatformElementValue_v1':identifier})
            assert deserialize_object(element).identifier==identifier
            actions=[]
            for section in item._fields.get('InspectorSectionsValue_v1',[]):
                for attribute in section._fields.get('ElementAttributesValue_v1',[]):
                    fields=attribute._fields
                    if fields.get('AttributeNameValue_v1')=='AXAction-2010' and fields.get('PerformsActionValue_v1'):
                        actions.append(fields)
            if len(actions)!=1:raise ValueError('系统未提供唯一激活动作')
            path=ROOT/'diagnostics'/('native-action-'+args.role+'.json')
            path.write_text(json.dumps({'role':args.role,'caption':item.caption,'requested_at':time.time()},ensure_ascii=False),encoding='utf-8')
            print(json.dumps({'status':'native_action_requested','role':args.role,'caption':item.caption},ensure_ascii=True),flush=True)
            await service._invoke('deviceElement:performAction:withValue:',element,serialize('AXAuditElementAttribute_v1',actions[0]),0,expects_reply=False)
            await asyncio.sleep(1)
    finally:await lockdown.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--udid',required=True)
    parser.add_argument('--role',choices=['back','input','unread','send'],required=True)
    parser.add_argument('--contact');parser.add_argument('--text');args=parser.parse_args()
    if args.role=='send' and (not args.contact or not args.text):parser.error('Sending requires exact contact and text')
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
