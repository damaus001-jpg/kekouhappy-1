"""Read notification-center accessibility captions without opening messages."""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from native_conversation import NativeConversation
from native_workspace import ROOT
from native_ui_scan import scan
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit


async def swipe(phone, start, end):
    try:
        for step in range(25):
            y = round((start + (end-start)*step/24)*65535)
            phone.request(phone.base, '/touch', {'type':'contact', 'x':32768, 'y':y})
            await asyncio.sleep(.025)
    finally:
        phone.request(phone.base, '/touch', {'type':'release', 'x':32768, 'y':round(end*65535)})
    await asyncio.sleep(.6)


async def main(args):
    phone = NativeConversation()
    phone.base = 'http://127.0.0.1:8080'
    phone.request('http://127.0.0.1:8070', '/api/select', {'udid':args.device})
    lockdown = await create_using_usbmux(serial=args.device, connection_type='USB',
        usbmux_address='127.0.0.1:27015', pairing_records_cache_folder=ROOT, autopair=False)
    try:
        async with AccessibilityAudit(lockdown) as service:
            if args.open:
                await swipe(phone, .002, .82)
            if args.close:
                await swipe(phone, .995, .20)
            deadline = time.monotonic() + args.watch
            while True:
                items = await scan(service, limit=600, seconds=15, settle=0)
                message_notifications = [item.caption for item in items
                    if (item.caption or '').upper().startswith(('MESSAGES,', 'MESSAGE,', '信息,', '短信,'))]
                if message_notifications or time.monotonic() >= deadline:
                    break
                await asyncio.sleep(2)
            result = {'device':args.device, 'created':datetime.now(timezone.utc).isoformat(),
                      'complete':items.complete, 'reason':items.reason, 'seconds':items.elapsed,
                      'elements':[{'caption':item.caption or '',
                                   'platform_identifier':item.platform_identifier} for item in items]}
            destination = ROOT/'diagnostics'/'notification-center-probe.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            if args.watch:
                print(json.dumps({'complete':items.complete, 'seconds':items.elapsed,
                    'notification_center':any(item.caption=='Notification Center, Header' for item in items),
                    'message_notifications':message_notifications}, ensure_ascii=True), flush=True)
            else:
                print(json.dumps(result, ensure_ascii=True), flush=True)
    finally:
        await lockdown.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='00008030-001119CE0A93402E')
    parser.add_argument('--watch', type=float, default=0)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--open', action='store_true')
    actions.add_argument('--close', action='store_true')
    args = parser.parse_args()
    if sys.platform=='win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main(args))
