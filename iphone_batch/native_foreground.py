"""Small title checks and bounded reverse reads; no taps, gestures or sends."""
import asyncio
import hashlib
import json
import re
from pymobiledevice3.services.accessibilityaudit import Direction, deserialize_object
from native_conversation import phone_key
from native_ui_scan import scan
from bubble_records import parse_bubbles
from message_ledger import append_verified_window
from pathlib import Path

TITLE_MARKERS = (
    (', Show Conversation Details, Button', ('', ', Double tap for additional contact options')),
    (', 显示对话详细信息, 按钮', ('', ', 轻点两下显示其他联系信息选项')),
)


async def run_foreground(service, action, options):
    """Let the worker release AX monitoring before its parent terminates it."""
    owner = asyncio.current_task()
    cancel_path = options.get('cancel_path')
    async def watch():
        while True:
            if cancel_path and Path(cancel_path).exists():
                owner.cancel()
                return
            await asyncio.sleep(.025)
    watcher = asyncio.create_task(watch())
    try:
        if action == 'auto_probe':
            return await probe_title(service, recover_first=options.get('recover_first', False))
        return await read_window(service, options, tail=action == 'auto_tail')
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


def title_number(caption):
    if not isinstance(caption, str):
        return None
    for marker, hints in TITLE_MARKERS:
        title, found, hint = caption.partition(marker)
        if found and hint in hints and re.fullmatch(r'\+?[0-9\s().-]+', title.strip()):
            return phone_key(title.replace('.', '').strip())
    return None


async def probe_title(service, *, recover_first=False):
    count, monitoring = 0, False
    try:
        async with asyncio.timeout(.8):
            monitoring = True
            await service.set_app_monitoring_enabled(True)
            await service.set_monitored_event_type()
            while not service._event_queue.empty():
                service._event_queue.get_nowait()
            if recover_first:
                await service.move_focus_next()
            else:
                await service.move_focus(Direction.First)
            previous = None
            while count < 3:
                name, args = await service._event_queue.get()
                if name != 'hostInspectorCurrentElementChanged:':
                    continue
                data = deserialize_object(service._extract_event_payload(args))
                items = data if isinstance(data, list) else [data]
                if not items:
                    continue
                item = items[0]
                key = (item.platform_identifier, item.caption)
                if key == previous:
                    continue
                previous = key
                count += 1
                number = title_number(item.caption)
                if number:
                    contact = next(item.caption.partition(marker)[0].strip() for marker, _ in TITLE_MARKERS if marker in item.caption)
                    return {'found': True, 'phone_number': number, 'contact': contact, 'elements_checked': count}
                if count < 3:
                    if recover_first and count == 1:
                        await service.move_focus(Direction.First)
                    else:
                        await service.move_focus_next()
    except TimeoutError:
        return {'found': False, 'reason': 'timeout', 'elements_checked': count}
    finally:
        if monitoring:
            try:
                await asyncio.wait_for(service.set_app_monitoring_enabled(False), .1)
            except Exception:
                pass
    return {'found': False, 'reason': 'not_conversation', 'elements_checked': count}


async def confirmed_title(service):
    result = await probe_title(service)
    if not result.get('found') and result.get('reason') == 'timeout' and not result.get('elements_checked'):
        result = await probe_title(service, recover_first=True)
    return result


async def read_window(service, options, *, tail=False):
    expected = options['phone_number']
    contact = options.get('contact') or expected
    observed, stop = [], {'reason': None}
    history = options.get('history') or []

    def finished(item):
        observed.append({'caption': item.caption or '', 'platform_identifier': item.platform_identifier})
        caption = item.caption or ''
        empty_composers = ('Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS')
        if (caption.startswith('Message, ') and caption not in empty_composers) or caption.startswith('Send, Button'):
            stop['reason'] = 'input_active'
            return True
        if any(marker in caption for marker, _ in TITLE_MARKERS):
            stop['reason'] = 'title'
            return True
        messages, _ = parse_bubbles(list(reversed(observed)), contact)
        if tail:
            if len(messages) >= 6:
                stop['reason'] = 'tail'
                return True
        elif history and messages and options.get('allow_overlap_stop', True):
            _, aligned = append_verified_window(history, messages)
            if aligned:
                stop['reason'] = 'overlap'
                return True
        return False

    scanned = await scan(service, limit=32 if tail else 600, seconds=1.5 if tail else 18,
                         settle=0 if tail else .04, reverse=True, stop_when=finished)
    records = list(reversed(observed))
    if stop['reason'] == 'input_active':
        return {'phone_number': expected, 'input_active': True}
    messages, unknown = parse_bubbles(records, contact)
    signature = hashlib.sha256(json.dumps(
        [(m.get('side'), m.get('time'), m.get('kind'), m.get('text'), m.get('element_id'))
         for m in messages[-6:]], ensure_ascii=False).encode()).hexdigest() if messages else None
    context_fingerprint = hashlib.sha256(json.dumps(
        [(m['side'], m['text'], m.get('time'), m.get('kind')) for m in messages], ensure_ascii=False).encode()).hexdigest()
    return {'phone_number': expected, 'contact': contact, 'messages': messages,
            'unclassified': unknown, 'fingerprint': signature,
            'context_fingerprint': context_fingerprint,
            'bounded_complete': bool(stop['reason']), 'stop_reason': stop['reason'] or scanned.reason,
            'source': 'native-current' if not tail and stop['reason'] and not unknown else 'native-foreground',
            'read_mode': 'foreground-bounded', 'history_complete': False}
