"""Native conversation capture and verified one-shot sending."""
import argparse
import asyncio
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from difflib import SequenceMatcher

from pymobiledevice3 import common
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from native_conversation import NativeConversation, phone_key
from native_ui_scan import scan, ScanResult
from native_message_page import read_message_footer
from sms_collect import parse_records
from send_policy import validate_send_text
from fixed_coordinates import load_profile, check_layout, tap
from visual_composer import input_point, send_point

ROOT = Path(__file__).resolve().parent / '.device-data'
common._HOMEFOLDER = ROOT
from pairing_patch import open_paired_usb

def digest(messages):
    data = [(m['side'], m['text'], m.get('time'), m.get('kind')) for m in messages]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def recent_digest(messages):
    # Earlier bubbles can be virtualized differently during focus traversal.
    # The newest incoming, outgoing and final bubble must all stay unchanged.
    recent = []
    for side in ('incoming', 'outgoing'):
        recent.append(next((m for m in reversed(messages) if m['side']==side), None))
    recent.append(messages[-1] if messages else None)
    return hashlib.sha256(json.dumps([(m['side'],m['text'],m.get('time'),m.get('kind'))
        if m else None for m in recent],ensure_ascii=False).encode()).hexdigest()


def validate_snapshot(current, record):
    if current['context_fingerprint']==record['context_fingerprint']:
        return
    if not record.get('context') or recent_digest(current['messages'])!=recent_digest(record['context']):
        raise ValueError('最新会话消息已变化，请重新读取并生成回复')


def context(records):
    original_records = records
    titles = {r.get('caption', '').split(', Show Conversation Details, Button')[0]
              for r in records if ', Show Conversation Details, Button' in (r.get('caption') or '')}
    if len(titles) != 1:
        raise ValueError('请先在手机上打开一个已有短信会话，再读取当前会话')
    title = next(iter(titles))
    if title in ('New Message', 'New iMessage', 'New Text Message'):
        numbers = {phone_key(part) for r in records if ', Button' in (r.get('caption') or '')
                   for part in r['caption'].split(', ') if phone_key(part)}
        if len(numbers) != 1:
            raise ValueError('收件人完整号码未唯一确认')
        number = numbers.pop()
        records = [{**r, 'caption': r['caption'].replace(title+', Show Conversation Details, Button',
                   number+', Show Conversation Details, Button')} for r in records]
        records = [{**r, 'caption': number+r['caption'][r['caption'].find(', '):]
                    if ', ' in r['caption'] and phone_key(r['caption'].split(', ', 1)[0]) == number else r['caption']}
                   for r in records]
    contact, _, _ = parse_records(records)
    from bubble_records import parse_bubbles
    messages, unknown = parse_bubbles(records, contact)
    if not messages:
        raise ValueError('当前会话未读到可确认的消息，未发送')
    return {'contact': contact, 'phone_number': phone_key(contact), 'messages': messages,
            'context_fingerprint': digest(messages), 'raw_elements': original_records,
            'unclassified': unknown, 'source': 'native-current'}


async def read(service, start_from_last=True):
    scanned = await scan(service, limit=3000, seconds=22, settle=0,
                         start_from_last=start_from_last)
    if not scanned.complete:
        scanned = await scan(service, limit=3000, seconds=22, settle=.04,
                             start_from_last=start_from_last)
    if not scanned.complete:
        raise ValueError(f'会话遍历未完整确认（{scanned.reason}，已读 {len(scanned)} 个元素），未执行新的发送操作')
    records = [{'caption': item.caption or '', 'platform_identifier': item.platform_identifier}
               for item in scanned]
    return context(records)


async def identify_conversation(service):
    # A header identifies the recipient only. No bubble or history boundary is
    # inferred, so a photo blocking focus cannot prevent database extraction.
    scanned = await scan(service, limit=3000, seconds=22, settle=0,
                         stop_when=lambda item: ', Show Conversation Details, Button' in (item.caption or ''))
    titles = {item.caption.split(', Show Conversation Details, Button')[0]
              for item in scanned if ', Show Conversation Details, Button' in (item.caption or '')}
    if len(titles) != 1 or not phone_key(next(iter(titles))):
        raise ValueError('未确认当前会话的完整电话号码，请打开目标短信会话后重试')
    contact = next(iter(titles))
    return {'contact': contact, 'phone_number': phone_key(contact)}


def merge_history_messages(existing, incoming):
    def key(message):
        return (message['side'], message['text'], message.get('time'), message.get('kind'))
    before, after = list(map(key, existing)), list(map(key, incoming))
    matcher = SequenceMatcher(None, before, after, autojunk=False)
    if existing and incoming and not any(block.size for block in matcher.get_matching_blocks()):
        return existing, False
    merged = []
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == 'equal':
            from bubble_status import update_status
            from copy import deepcopy
            for old, new in zip(existing[a:b], incoming[c:d]):
                message = deepcopy(old)
                if new.get('bubble_status'):
                    update_status(message, new['bubble_status'])
                merged.append(message)
        elif tag == 'delete':
            merged.extend(existing[a:b])
        elif tag == 'insert':
            merged.extend(incoming[c:d])
        else:
            # Conflicting order is evidence of changing/virtualized elements.
            # Keep the original occurrence order; never invent a complete history.
            return existing, False
    return merged, True


async def scroll_history(phone, toward_top):
    start, end = (.30, .78) if toward_top else (.78, .30)
    try:
        for step in range(19):
            phone.request(phone.base, '/touch', {'type':'contact', 'x':32768,
                'y':round((start+(end-start)*step/18)*65535)})
            await asyncio.sleep(.025)
    finally:
        phone.request(phone.base, '/touch', {'type':'release', 'x':32768, 'y':round(end*65535)})
    await asyncio.sleep(.5)


async def capture_history(service, phone):
    started = time.monotonic()
    initial = await read(service)
    key = initial['phone_number']
    snapshots = [initial]
    # Load older messages before traversing them. A focus cycle alone only
    # describes currently loaded elements and is never a history boundary.
    for _ in range(8):
        await scroll_history(phone, True)
    first = await read(service, start_from_last=False)
    if first['phone_number'] != key:
        raise ValueError('读取期间会话发生切换，已停止')
    snapshots.append(first)
    stable = 0
    last_signature = digest(first['messages'])
    for _ in range(12):
        if time.monotonic()-started > 80:
            break
        await scroll_history(phone, False)
        try:
            page = await read(service, start_from_last=False)
        except ValueError:
            break
        if page['phone_number'] != key:
            raise ValueError('读取期间会话发生切换，已停止')
        snapshots.append(page)
        signature = digest(page['messages'])
        stable = stable+1 if signature == last_signature else 0
        last_signature = signature
        if stable >= 2:
            break
    best = max(snapshots, key=lambda page:len(page['messages']))
    messages = best['messages']
    aligned = True
    for page in snapshots:
        messages, matches = merge_history_messages(messages, page['messages'])
        aligned = aligned and matches
    for index, message in enumerate(messages, 1):
        message['sequence'] = index
    best.update(messages=messages, context_fingerprint=digest(messages), history_complete=False,
                history_pages=len(snapshots), history_alignment=aligned,
                scope=f'已向上回看并逐段读取 {len(snapshots)} 次，共 {len(messages)} 条；系统历史边界尚未确认，重复消息保留')
    return best


def unread_records(records):
    if not any(r['caption'] in ('Messages, Header', 'Unread, Header') for r in records):
        raise ValueError('未确认短信列表页面')
    rows = []
    seen = set()
    for index, r in enumerate(records):
        caption = r.get('caption') or ''
        if ', Unread, ' not in caption:
            continue
        name, preview = caption.split(', Unread, ', 1)
        identifier = r.get('platform_identifier') or str(index)
        row_key = (identifier, caption)
        if row_key in seen:
            continue
        seen.add(row_key)
        rows.append({'name': name, 'phone_number': phone_key(name), 'preview': preview,
                     'element_id': identifier, 'clickable': bool(phone_key(name))})
    return rows


async def raw_page(service, full=False, settle=0):
    scanned = await scan(service, limit=20000 if full else 100,
                         seconds=45 if full else 12, settle=settle)
    records = ScanResult({'caption': i.caption or '', 'platform_identifier': i.platform_identifier}
                         for i in scanned)
    records.complete, records.reason, records.elapsed = scanned.complete, scanned.reason, scanned.elapsed
    return records


async def compose_toolbar(service):
    """Recognize the Messages list using its fixed footer only."""
    footer = await read_message_footer(service)
    if footer['page_type'] != 'message_list' or not footer['compose_available']:
        return None
    records = ScanResult(footer['raw_elements'])
    records.complete = False
    records.reason = 'compose_toolbar_verified'
    records.elapsed = footer['scan_seconds']
    return records


async def verified_list(service, initial):
    """Two matching full traversals; limited/silent scans are never called complete."""
    first = initial if initial.complete else await raw_page(service, full=True)
    unread_records(first)
    second = await raw_page(service, full=True, settle=0 if first.complete else .04)
    unread_records(second)
    stable = first.complete and second.complete and [r['caption'] for r in first]==[r['caption'] for r in second]
    # Preserve observations from either pass, including a newly arriving unread row.
    # Inspector identifiers can change between passes. Match occurrences of
    # each caption, preserving distinct identical rows without doubling a pass.
    unique = {}
    for items in (unread_records(first), unread_records(second)):
        occurrences = {}
        for row in items:
            caption = (row['name'], row['preview'])
            occurrences[caption] = occurrences.get(caption, 0)+1
            unique[(*caption, occurrences[caption])] = row
    elapsed = round(first.elapsed+second.elapsed,2)
    return {'items':list(unique.values()), 'complete':bool(stable), 'seconds':elapsed,
            'scanned_elements':len(second), 'reason':'stable_full_traversal' if stable else second.reason if not second.complete else 'list_changed',
            'scope':('当前列表已连续两次完整遍历并核对一致' if stable else '遍历尚未确认完整，请再次刷新；已保留本次发现的未读联系人')+f' · {elapsed} 秒'}


def composer_is_empty(captions):
    placeholders = ('Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS')
    return (any(c in placeholders for c in captions)
            and not any(c.startswith('Send, Button') for c in captions))


async def reopen_reply_recipient(service, phone, record):
    key = record['phone_number']
    await phone.chord(0x11)
    await asyncio.sleep(.4)
    captions = [r['caption'] for r in await raw_page(service)]
    if 'To:' not in captions or 'Message' not in captions or not any(
            c.startswith('New Message, Show Conversation Details') for c in captions):
        raise ValueError('未确认空白收件人输入栏，未输入回复')
    await phone.paste(key)
    await asyncio.sleep(.4)
    captions = [r['caption'] for r in await raw_page(service)]
    if not any(c.startswith('To:, ') and phone_key(c[5:]) == key for c in captions):
        raise ValueError('重新输入的完整号码未确认，未输入回复')
    await phone.keys([0x28])
    await phone.keys([])
    await asyncio.sleep(.6)
    current = await read(service)
    if current['phone_number'] != key:
        raise ValueError('重新打开的收件人不一致，未输入回复')
    validate_snapshot(current, record)
    if not composer_is_empty([r['caption'] for r in current['raw_elements']]):
        raise ValueError('重新打开的会话存在草稿，已保留原内容')
    return current


async def focus_current_composer(phone, current, record):
    if current.get('phone_number')!=record.get('phone_number'):
        raise ValueError('当前手机会话号码不一致，未切换或发送')
    validate_snapshot(current,record)
    if not composer_is_empty([row['caption'] for row in current['raw_elements']]):
        raise ValueError('当前手机输入框存在草稿，已保留原内容')
    placeholders = ('Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS')
    inputs = [row for row in current['raw_elements'] if row['caption'] in placeholders]
    if len(inputs) != 1:
        raise ValueError('未找到唯一短信输入框，未输入或发送')
    point = await asyncio.to_thread(input_point, phone)
    await tap(phone, point)


async def verify_reply_context(service, phone, current, record, *, prepared_body=False, prepared_text=None):
    """Expose newer bubbles before judging an older viewport stale; never type."""
    async with asyncio.timeout(25):
        for attempt in range(4):
            if current.get('phone_number') != record.get('phone_number'):
                raise ValueError('当前会话未核验到相同的完整号码，未输入或发送')
            if prepared_body:
                prepared_send_control(current, record['phone_number'],
                                      record['english'] if prepared_text is None else prepared_text)
            elif not composer_is_empty([row['caption'] for row in current['raw_elements']]):
                raise ValueError('手机输入框存在草稿或状态未确认，已保留原内容')
            try:
                validate_snapshot(current, record)
                return current
            except ValueError:
                if attempt == 3:
                    raise ValueError('最新会话消息未能核对一致，未输入或发送；请重新读取当前会话后再回复') from None
            await scroll_history(phone, False)
            current = await read(service)


def prepared_send_control(prepared, number, text):
    if prepared.get('phone_number') != number:
        raise ValueError('粘贴后收件人发生变化，未执行发送')
    rows = prepared.get('raw_elements', [])
    # Accept only known accessibility traits following the exact intended body.
    suffixes = ('', ', Text Field', ', Text View', ', Text Message, SMS', ', iMessage')
    inputs = [row for row in rows if row['caption'] in {'Message, '+text+suffix for suffix in suffixes}]
    if len(inputs) != 1:
        raise ValueError('正文未成功填入手机短信输入框，或输入内容不一致；未执行发送')
    buttons = [row for row in rows if row['caption'].startswith('Send, Button')
               and 'Dimmed' not in row['caption'] and 'Disabled' not in row['caption']]
    if len(buttons) != 1:
        raise ValueError('手机发送按钮未就绪或不唯一，未执行发送')
    return buttons[0]


def failed_preparation(current, record, record_path):
    """Find our provably unsent phone body, including a newly edited reply."""
    if current.get('phone_number') != record.get('phone_number'):
        return None
    for path in record_path.parent.glob('*.json'):
        if path == record_path:
            continue
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(previous, dict):
            continue
        if (previous.get('status') != 'failed'
                or any(previous.get(key) != record.get(key) for key in ('device', 'phone_number'))):
            continue
        # Compatibility with the already failed capsule-detection attempt,
        # which predates the explicit verified-body marker below.
        if (previous.get('prepared_body_verified') is not True
                and previous.get('error') != '未定位到唯一可用的手机发送按钮，未执行发送'):
            continue
        try:
            prepared_send_control(current, record['phone_number'], previous['english'])
        except (ValueError, KeyError):
            continue
        return previous
    return None


def owns_failed_preparation(current, record, record_path):
    previous = failed_preparation(current, record, record_path)
    return bool(previous and previous['english'] == record['english'])


async def enter_compose_recipient(service, phone, number, *, verify_selection=False):
    key = phone_key(number or '')
    if not key:
        raise ValueError('需要完整联系人号码')
    # Match the smooth local follow-up-number path: normalize the current page
    # and preserve drafts before opening a fresh compose sheet.
    await list_page(service, phone, toolbar_only=True)
    await phone.chord(0x11)
    await asyncio.sleep(.3)
    captions = [r['caption'] for r in await raw_page(service)]
    if ('To:' not in captions or 'Message' not in captions or not any(
            c.startswith('New Message, Show Conversation Details') for c in captions)):
        raise ValueError('未确认空白收件人输入栏，已停止')
    await phone.paste(key)
    await asyncio.sleep(.3)
    captions = [r['caption'] for r in await raw_page(service)]
    if not any(c.startswith('To:, ') and phone_key(c[5:]) == key for c in captions):
        raise ValueError('输入的完整号码未确认，未打开会话')
    await phone.keys([0x28])
    await phone.keys([])
    await asyncio.sleep(.5)
    if not verify_selection:
        return None
    selected = await raw_page(service)
    if not task_recipient_confirmed(selected, key):
        raise ValueError('选择后的完整收件号码未确认，未输入正文')
    if not composer_is_empty([row['caption'] for row in selected]):
        raise ValueError('收件会话中存在草稿，已保留原内容')
    return selected


async def open_phone_conversation(service, phone, number):
    key = phone_key(number or '')
    if not key:
        raise ValueError('需要完整联系人号码')
    await enter_compose_recipient(service, phone, key)
    current = await read(service)
    if current['phone_number'] != key:
        raise ValueError('打开后的会话号码未确认')
    return current


async def list_page(service, phone, toolbar_only=False):
    if toolbar_only:
        toolbar = await compose_toolbar(service)
        if toolbar is not None:
            return toolbar
    records = await raw_page(service)
    if any(', Show Conversation Details, Button' in r['caption'] for r in records):
        # Returning to the list is intentional, but never discard an existing draft.
        captions = [r['caption'] for r in records]
        context(records)
        if not composer_is_empty(captions):
            raise ValueError('手机有未发送草稿，请先处理草稿；没有切换会话')
        # Standard edge-back gesture requested by the user, independent of screenshots.
        try:
            for step in range(19):
                x = round((.015 + (.78-.015)*step/18)*65535)
                phone.request(phone.base,'/touch',{'type':'contact','x':x,'y':32768})
                await asyncio.sleep(.025)
        finally:
            phone.request(phone.base,'/touch',{'type':'release','x':round(.78*65535),'y':32768})
        await asyncio.sleep(.4)
        if toolbar_only:
            toolbar = await compose_toolbar(service)
            if toolbar is not None:
                return toolbar
        records = await raw_page(service)
    try:
        unread_records(records)
    except ValueError:
        # Retry a truncated/unstable initial pass at a conservative pace.
        records = await raw_page(service, full=True)
        try:
            unread_records(records)
        except ValueError:
            records = await raw_page(service, full=True, settle=.04)
            unread_records(records)
    return records


def task_recipient_confirmed(records, number):
    key = phone_key(number)
    return bool(key and any(
        ', Button' in (row.get('caption') or '') and
        any(phone_key(part) == key for part in row['caption'].split(', '))
        for row in records))


def write_task_unit(path, value, status, *, error=None, sent_at=None):
    from sms_tasks import SmsTaskRunner
    SmsTaskRunner.write_unit_status(path, value, status, error=error, sent_at=sent_at)


async def send_task_unit(service, args, record_path):
    """Send one persisted task unit only after exact recipient/body checks."""
    task_root = (ROOT/'workspace'/'sms-tasks').resolve()
    try:
        relative = record_path.relative_to(task_root)
    except ValueError:
        raise ValueError('短信任务记录路径无效') from None
    if (len(relative.parts) != 3 or relative.parts[1] != 'items' or
            not re.fullmatch(r'[a-f0-9]{32}', relative.parts[0]) or
            not re.fullmatch(r'\d{5}\.json', relative.parts[2])):
        raise ValueError('短信任务记录路径无效')
    record = json.loads(record_path.read_text(encoding='utf-8'))
    task_id = relative.parts[0]
    if (record.get('version') != 1 or record.get('task_id') != task_id or
            record.get('device') != args.device or record.get('status') != 'ready'):
        raise ValueError('短信任务记录状态或设备不匹配')
    number = record.get('number')
    text = validate_send_text(record.get('text'))
    if not re.fullmatch(r'\+[1-9][0-9]{6,14}', str(number or '')):
        raise ValueError('短信任务号码无效')
    phone = NativeConversation(); phone.base = args.base

    # Follow the same normalized page-opening route as a click on the local
    # follow-up number list. A brand-new recipient has no history to read yet,
    # so the verified recipient chip and empty composer are enough to proceed.
    selected_elements = await enter_compose_recipient(
        service, phone, number, verify_selection=True)
    try:
        selected = await read(service)
    except ValueError as exc:
        if str(exc) != '当前会话未读到可确认的消息，未发送':
            raise
        selected = {'phone_number': number, 'messages': [],
                    'raw_elements': selected_elements}
    selected_captions = [row['caption'] for row in selected.get('raw_elements', [])]
    if (selected.get('phone_number') != number or
            not task_recipient_confirmed(selected.get('raw_elements', []), number)):
        raise ValueError('手机未确认完全匹配的收件号码；任务未发送')
    if not composer_is_empty(selected_captions):
        raise ValueError('新短信输入框非空，已保留手机草稿；任务未发送')
    before_count = sum(m.get('side') == 'outgoing' and m.get('text') == text
                       for m in selected.get('messages', []))

    point = await asyncio.to_thread(input_point, phone)
    await tap(phone, point)
    await phone.paste(text)
    await asyncio.sleep(.5)
    prepared = await raw_page(service)
    prepared_send_control({'phone_number': number, 'raw_elements': prepared}, number, text)
    send_location = await asyncio.to_thread(send_point, phone)

    # This durable marker is written before the irreversible tap. A restart after
    # this point is treated as uncertain and the task runner will never retry it.
    record.update(status='send_requested', send_requested_at=datetime.now().astimezone().isoformat())
    write_task_unit(record_path, record, 'send_requested')
    await tap(phone, send_location)
    await asyncio.sleep(1)
    after = await read(service)
    after_count = sum(m.get('side') == 'outgoing' and m.get('text') == text
                      for m in after.get('messages', []))
    if after.get('phone_number') != number or after_count <= before_count or any(
            row.get('caption') == 'Message, ' + text for row in after.get('raw_elements', [])):
        raise RuntimeError('发送结果未确认；请核对手机，系统不会自动重发')
    sent_at = datetime.now().astimezone().isoformat()
    write_task_unit(record_path, record, 'sent_verified', sent_at=sent_at)
    return {'status': 'sent_verified', 'device': args.device, 'phone_number': number,
            'sent_at': sent_at}


async def run(args):
    lockdown = await open_paired_usb(args.device, ROOT)
    try:
        async with AccessibilityAudit(lockdown) as service:
            if args.action == 'banner':
                from message_banner import observe
                return await observe(service, lockdown, args.device)
            if args.action == 'page':
                return {'device': args.device, **await read_message_footer(service)}
            if args.action in ('auto_probe', 'auto_tail', 'auto_read', 'auto_sent_tail'):
                from native_foreground import run_foreground
                record_path = Path(args.record).resolve()
                if record_path.parent != (ROOT/'workspace'/'foreground').resolve():
                    raise ValueError('自动读取任务路径无效')
                options = json.loads(record_path.read_text(encoding='utf-8'))
                if options.get('cancel_path') != str(record_path.with_suffix('.cancel')):
                    raise ValueError('自动读取取消标记无效')
                return await run_foreground(service, args.action, options)
            if args.action in ('notifications', 'open_notification'):
                from message_notifications import discover, open_notification
                phone = NativeConversation(); phone.base = args.base
                if args.action=='notifications':
                    return {'device':args.device, **await discover(service, phone, args.device)}
                record_path = Path(args.record).resolve()
                if record_path.parent != (ROOT/'workspace'/'notifications').resolve():
                    raise ValueError('通知记录路径无效')
                expected = json.loads(record_path.read_text(encoding='utf-8'))
                return await open_notification(service, phone, args.device, expected, context)
            if args.action == 'open':
                phone = NativeConversation(); phone.base = args.base
                return {'device':args.device, **await open_phone_conversation(service, phone, args.phone)}
            if args.action == 'campaign_send':
                if not args.record:
                    raise ValueError('短信任务记录缺失')
                return await send_task_unit(service, args, Path(args.record).resolve())
            if args.action == 'unread':
                phone = NativeConversation(); phone.base = args.base
                records = await list_page(service, phone)
                return {'device': args.device, **await verified_list(service, records)}
            if args.action == 'history':
                phone = NativeConversation(); phone.base = args.base
                return {'device': args.device, **await capture_history(service, phone)}
            if args.action == 'identify':
                return {'device': args.device, **await identify_conversation(service)}
            if args.action == 'capture':
                from ax_conversation import capture_conversation
                from message_ledger import MessageLedger
                identity = await identify_conversation(service)
                prior = MessageLedger(ROOT).load(args.device, identity['phone_number']) or {}
                return {'device': args.device, **await capture_conversation(service,
                    {'device': args.device, 'phone_number': identity['phone_number'], 'history': prior.get('messages', []),
                     'allow_overlap_stop': not bool(prior.get('pending_windows'))})}
            if args.action == 'latest':
                phone = NativeConversation(); phone.base = args.base
                # A bounded attempt to expose the newest loaded bubbles. If
                # their checkpoint is still absent, the caller uses the DB.
                for _ in range(3):
                    await scroll_history(phone, False)
                return {'device': args.device, **await read(service)}
            current = await read(service)
            record_path = Path(args.record).resolve()
            if record_path.parent != (ROOT/'workspace'/'replies').resolve():
                raise ValueError('回复记录路径无效')
            record = json.loads(record_path.read_text(encoding='utf-8'))
            key = record.get('phone_number')
            if record['device'] != args.device or not key or current['phone_number'] != key:
                raise ValueError('当前会话未核验到相同的完整号码，请读取正确的号码会话后重新生成回复')
            text = validate_send_text(record['english'])
            if record.get('status') != 'draft':
                raise ValueError('这条回复已处理，不可重复发送')
            phone = NativeConversation(); phone.base = args.base
            previous_preparation = failed_preparation(current, record, record_path)
            previous_text = previous_preparation['english'] if previous_preparation else None
            reuse_prepared = previous_text == text
            current = await verify_reply_context(service, phone, current, record,
                                                 prepared_body=previous_preparation is not None,
                                                 prepared_text=previous_text)
            if previous_preparation:
                validate_snapshot(current, previous_preparation)
            captions = [r['caption'] for r in current['raw_elements']]
            profile = load_profile(args.device)
            if reuse_prepared:
                prepared = current
            else:
                if profile:
                    await check_layout(phone, profile, captions)
                    await tap(phone, profile['input'])
                elif previous_preparation:
                    await tap(phone, await asyncio.to_thread(input_point, phone))
                else:
                    await focus_current_composer(phone, current, record)
                if previous_preparation:
                    # Recheck the owned body after focus before replacing it.
                    focused = await read(service)
                    prepared_send_control(focused, key, previous_text)
                    validate_snapshot(focused, record)
                    await phone.chord(0x04)  # Select only our verified old composer body.
                await phone.paste(text)
                await asyncio.sleep(.5)
                prepared = await read(service)
            prepared_captions = [r['caption'] for r in prepared['raw_elements']]
            prepared_send_control(prepared, key, text)
            record['prepared_body_verified'] = True
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            if profile:
                await check_layout(phone, profile, prepared_captions)
            else:
                send_location = await asyncio.to_thread(send_point, phone)
            # Persist before Return. No retry is allowed after this point.
            record['status'] = 'send_requested'
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            if profile:
                await tap(phone, profile['send'])
            else:
                await tap(phone, send_location)
            await asyncio.sleep(1)
            after = await read(service)
            before_count = sum(m['side']=='outgoing' and m['text']==text for m in current['messages'])
            after_count = sum(m['side']=='outgoing' and m['text']==text for m in after['messages'])
            if after['phone_number'] != key or after_count <= before_count or any(r['caption']=='Message, '+text for r in after['raw_elements']):
                raise RuntimeError('发送结果未确认，请在手机核对；禁止自动重发')
            sent_captions = [r['caption'] for r in after['raw_elements']]
            outgoing = re.compile(r'^Your (?:iMessage|Message|SMS|Text Message), '+re.escape(text)+r', \d{1,2}:\d{2}(?:,|$)')
            delivered = any(outgoing.search(c) and i+1<len(sent_captions) and sent_captions[i+1]=='Delivered'
                            for i,c in enumerate(sent_captions))
            record.update(status='sent_verified', delivered=delivered)
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            sent_message = next(m for m in reversed(after['messages'])
                                if m['side']=='outgoing' and m['text']==text)
            return {'status': 'sent_verified', 'delivered': delivered, 'device': args.device,
                    'contact': key, 'conversation': after, 'sent_message': sent_message}
    finally:
        await lockdown.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True)
    parser.add_argument('--action', choices=['page', 'auto_probe', 'auto_tail', 'auto_read', 'auto_sent_tail', 'capture', 'latest', 'identify', 'history', 'send', 'campaign_send', 'unread', 'open', 'notifications', 'open_notification', 'banner'], required=True)
    parser.add_argument('--base'); parser.add_argument('--record')
    parser.add_argument('--phone')
    args = parser.parse_args()
    if sys.platform == 'win32': asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        result = asyncio.run(run(args))
        print(json.dumps(result, ensure_ascii=True), flush=True)
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=True), flush=True)
        sys.exit(1)
