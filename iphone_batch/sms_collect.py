"""Bounded, explicit accessibility traversal of the open Messages conversation.

No OCR, translation calls, message activation, or text-based deduplication.
Element identifiers may be recycled by the Messages list during scrolling.
"""
import argparse
import asyncio
from datetime import datetime
import html
import json
from pathlib import Path
import re
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent / '.device-data'
TIME = re.compile(r', (\d{1,2}:\d{2}(?:\s*[AP]M)?)(?P<traits>(?:, (?:Link|Button|Image))*)$')


def parse_records(records):
    contact = None
    for record in records:
        text = record.get('caption') or ''
        marker = ', Show Conversation Details, Button'
        if marker in text:
            contact = text.split(marker, 1)[0]
            break
    messages = []
    unclassified = []
    for record in records:
        text = record.get('caption') or ''
        match = TIME.search(text)
        if not match:
            continue
        content = text[:match.start()]
        side = None
        for prefix in ('Your iMessage, ', 'Your Message, ', 'Your SMS, '):
            if content.startswith(prefix):
                side = 'outgoing'
                content = content[len(prefix):]
                break
        if side is None and contact and content.startswith(contact + ', '):
            side = 'incoming'
            content = content[len(contact) + 2:]
        if side is None:
            unclassified.append(record)
            continue
        messages.append({'sequence': len(messages) + 1, 'side': side,
                         'time': match[1], 'text': content,
                         'kind': 'attachment' if content == 'Includes picture' else 'text',
                         'traits': match['traits'].lstrip(', ').split(', ') if match['traits'] else [],
                         'element_id': record.get('platform_identifier'),
                         'raw_caption': text})
    return contact, messages, unclassified


def save_result(udid, records, reason, elapsed, output, *, reviewed_messages=None, review=None):
    contact, messages, unclassified = parse_records(records)
    if reviewed_messages is not None:
        messages = reviewed_messages
    result = {'device': udid, 'created': datetime.now().isoformat(),
              'contact': contact, 'stop_reason': reason, 'elapsed_seconds': round(elapsed, 2),
              'scope': 'Focus traversal; full history completeness requires verification',
              'messages': messages, 'unclassified': unclassified, 'raw_elements': records}
    if review is not None:
        result['review'] = review
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    text_messages = [message for message in messages if message['kind'] == 'text']
    for number, message in enumerate(text_messages, 1):
        side = '我方' if message['side'] == 'outgoing' else '对方'
        content = '图片消息（尚未提取图片内容）' if message['kind'] == 'attachment' else message['text']
        rows.append('<article><b>' + str(number) + ' · ' + side + ' · '
                    + html.escape(message['time']) + '</b><pre>' + html.escape(content) + '</pre></article>')
    raw = ''.join('<li><pre>' + html.escape(record.get('caption') or '[空文字]') + '</pre></li>' for record in records)
    document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>短信自动收集核对</title><style>body{font:16px system-ui;max-width:900px;margin:30px auto;padding:0 20px}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-bottom:1px solid #ddd;padding:14px 0}</style>'
                '<h1>短信自动收集核对</h1><p>联系人：' + html.escape(contact or '未识别')
                + '。已整理 ' + str(len(text_messages)) + ' 条文字消息，图片已跳过。停止原因：' + html.escape(reason)
                + '。</p>' + ('<p>' + html.escape(review['note']) + '</p>' if review else '')
                + '<p>没有使用 OCR，没有调用 DeepSeek。'
                + ('本次文字结果已由用户核对；' if review else '完整性与时间顺序尚需核对；')
                + '相同文字的消息没有合并。这里只保留接口提供的时分，尚未解析日期。</p>'
                + ''.join(rows) + '<details><summary>查看全部原始界面文字（含未分类内容）</summary><ol>' + raw
                + '</ol></details></html>')
    output.with_suffix('.html').write_text(document, encoding='utf-8')
    return {'messages': len(messages), 'unclassified': len(unclassified),
            'elements': len(records), 'stop_reason': reason,
            'elapsed_seconds': round(elapsed, 2), 'review_page': str(output.with_suffix('.html'))}


async def collect(args):
    from pymobiledevice3 import common
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit, Direction, deserialize_object
    common._HOMEFOLDER = ROOT
    records = []
    started = time.monotonic()
    reason = 'element_limit'
    output = ROOT / 'diagnostics' / ('sms-collected-' + args.udid[-8:] + ('-' + args.label if args.label else ''))
    stop_file = ROOT / ('sms-stop-' + args.udid[-8:])
    if stop_file.exists():
        raise RuntimeError('Stop file exists; remove it before intentionally starting another scan')
    journal = output.with_suffix('.jsonl')
    journal.parent.mkdir(parents=True, exist_ok=True)
    lockdown = None
    try:
        lockdown = await create_using_usbmux(serial=args.udid, connection_type='USB',
            usbmux_address='127.0.0.1:27015', pairing_records_cache_folder=ROOT, autopair=False)
        async with AccessibilityAudit(lockdown) as service:
            await service.set_show_visuals(False)
            await service.set_app_monitoring_enabled(True)
            await service.set_monitored_event_type()
            queue = service._event_queue
            while not queue.empty():
                queue.get_nowait()
            await service.move_focus(Direction.Last if args.direction == 'reverse' else Direction.First)
            anchor = None
            silence_count = 0
            with journal.open('w', encoding='utf-8') as stream:
                try:
                    while len(records) < args.max_elements:
                        if stop_file.exists():
                            reason = 'user_stopped'
                            break
                        if time.monotonic() - started >= args.max_seconds:
                            reason = 'time_limit'
                            break
                        try:
                            name, payload = await asyncio.wait_for(queue.get(), timeout=1)
                        except asyncio.TimeoutError:
                            silence_count += 1
                            if silence_count >= 5:
                                reason = 'focus_timeout'
                                break
                            await service.move_focus(Direction.Previous if args.direction == 'reverse' else Direction.Next)
                            continue
                        silence_count = 0
                        if name != 'hostInspectorCurrentElementChanged:':
                            continue
                        event = deserialize_object(service._extract_event_payload(payload))
                        if isinstance(event, list):
                            event = event[0] if event else None
                        if event is None:
                            continue
                        try:
                            record = event.to_dict()
                        except (KeyError, ValueError):
                            # Some focus events have text but no usable platform identifier.
                            # Keep the text; a recycled/missing UI identifier is not a message ID.
                            record = {'caption': event.caption, 'spoken_description': event.spoken_description,
                                      'platform_identifier': None, 'estimated_uid': None}
                        key = (record['platform_identifier'], record.get('caption'))
                        if anchor is None:
                            anchor = key
                        elif key == anchor:
                            reason = 'focus_cycle'
                            break
                        record['sequence'] = len(records) + 1
                        records.append(record)
                        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                        stream.flush()
                        if len(records) % 10 == 0:
                            print(json.dumps({'status': 'collecting', 'elements': len(records),
                                'message_candidates': sum(bool(TIME.search(r.get('caption') or '')) for r in records),
                                'elapsed_seconds': round(time.monotonic() - started, 1)}), flush=True)
                        await asyncio.sleep(args.settle_ms / 1000)
                        await service.move_focus(Direction.Previous if args.direction == 'reverse' else Direction.Next)
                finally:
                    try:
                        await service.set_app_monitoring_enabled(False)
                    except Exception:
                        print(json.dumps({'status': 'monitor_cleanup_failed'}), flush=True)
    except Exception as error:
        reason = 'error_' + type(error).__name__
        print(json.dumps({'status': 'collection_error', 'error_type': type(error).__name__,
            'protocol_key': str(error.args[0]) if isinstance(error, KeyError) and error.args else None,
            'locations': [{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                          for frame in traceback.extract_tb(error.__traceback__)[-4:]]}), flush=True)
    finally:
        if lockdown is not None:
            await lockdown.close()
        chronological = list(reversed(records)) if args.direction == 'reverse' else records
        summary = save_result(args.udid, chronological, reason, time.monotonic() - started, output)
        print(json.dumps({'status': 'collection_finished', **summary}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--udid', required=True)
    parser.add_argument('--max-elements', type=int, default=500)
    parser.add_argument('--max-seconds', type=int, default=90)
    parser.add_argument('--direction', choices=['forward', 'reverse'], default='forward')
    parser.add_argument('--settle-ms', type=int, default=250)
    parser.add_argument('--label', choices=['verify-reverse', 'verify-forward'])
    args = parser.parse_args()
    if not 1 <= args.max_elements <= 2000 or not 1 <= args.max_seconds <= 300 or not 0 <= args.settle_ms <= 2000:
        parser.error('Invalid traversal limits')
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(collect(args))


if __name__ == '__main__':
    main()
