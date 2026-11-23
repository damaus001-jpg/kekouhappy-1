"""Small title checks and bounded reverse reads; no taps, gestures or sends."""
import asyncio
import hashlib
import json
import re
from pymobiledevice3.services.accessibilityaudit import Direction, deserialize_object
from native_conversation import phone_key
from native_ui_scan import scan
from bubble_records import date_separator, parse_bubbles
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
        if action == 'auto_read':
            from ax_conversation import capture_conversation
            return await capture_conversation(service, options)
        if action == 'auto_sent_tail':
            return await read_sent_tail(service, options)
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
            if hasattr(service, 'set_show_visuals'):
                await service.set_show_visuals(False)
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


async def read_sent_tail(service, options):
    title = await confirmed_title(service)
    if not title.get('found'):
        return {'phone_number': options['phone_number'], 'send_pending': True}
    if title['phone_number'] != options['phone_number']:
        return {'phone_number': title['phone_number'], 'changed': True}
    result = await read_window(service, {**options, 'contact': title['contact']}, tail=True)
    if result.get('input_active') or not result.get('messages'):
        return result
    from ax_bottom import move_focus, reach_bottom
    from ax_recheck import inspect_node
    from ax_traversal import focus_row
    deadline = asyncio.get_running_loop().time()+4
    async def move(direction):
        item = await move_focus(service, direction)
        other = title_number(item.caption or '')
        if other and other != options['phone_number']:
            raise ValueError('发送核验期间会话发生变化')
        return item
    async def inspect(item, *, deadline):
        return await inspect_node(focus_row(item), title['contact'], occurrence=0,
            query_label=lambda: service.element_attribute(item.element.identifier, 'Label'),
            deadline=deadline)
    await service.set_app_monitoring_enabled(True)
    await service.set_monitored_event_type()
    try:
        async with asyncio.timeout(4):
            bottom = await reach_bottom(move=move, inspect=inspect, deadline=deadline,
                                        anchor=result['messages'][-1])
        result['bottom_confirmed'] = bottom['confirmed']
        if bottom['confirmed']:
            result['messages'].extend(bottom['messages'][1:])
            result['context_fingerprint'] = hashlib.sha256(json.dumps(
                [(m['side'],m['text'],m.get('time'),m.get('kind')) for m in result['messages']],
                ensure_ascii=False).encode()).hexdigest()
    except (TimeoutError, ValueError):
        result['bottom_confirmed'] = False
    finally:
        await service.set_app_monitoring_enabled(False)
    return result


async def read_window(service, options, *, tail=False):
    expected = options['phone_number']
    contact = options.get('contact') or expected
    observed, stop = [], {'reason': None}
    empty_composer_seen = False
    history = options.get('history') or []
    relative_span = next((len(history)-i for i, m in enumerate(history)
                          if m.get('date_precision') == 'relative-label'
                          or (date_separator(m.get('date_label') or '') or {}).get('date_precision') == 'relative-label'), 0)

    def finished(item):
        nonlocal empty_composer_seen
        observed.append({'caption': item.caption or '', 'platform_identifier': item.platform_identifier})
        caption = item.caption or ''
        empty_composers = ('Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS')
        if caption in empty_composers:
            empty_composer_seen = True
        # Reverse traversal reaches the composer before message content. Link
        # previews also expose "Message, ..." labels; after the empty composer
        # was acknowledged, those labels are content, not an unsent draft.
        if (caption.startswith('Message, ') and caption not in empty_composers
                and not empty_composer_seen) or caption.startswith('Send, Button'):
            stop['reason'] = 'input_active'
            return True
        if any(marker in caption for marker, _ in TITLE_MARKERS):
            stop['reason'] = 'title'
            return True
        messages, _ = parse_bubbles(list(reversed(observed)), contact)
        if tail:
            if options.get('tail_limit') == 1 and messages:
                stop['reason'] = 'latest_watch'
                return True
            expected = options.get('expected_text')
            if history and expected is not None:
                merged, aligned = append_verified_window(history, messages)
                added = merged[len(history):] if aligned else []
                if any(m.get('side') == 'outgoing' and m.get('text') == expected for m in added):
                    stop['reason'] = 'verified_send_overlap'
                    return True
            if len(messages) >= 6 and (not relative_span or messages[-1].get('date_label')):
                stop['reason'] = 'tail'
                return True
        elif history and messages and options.get('allow_overlap_stop', True):
            merged, aligned = append_verified_window(history, messages)
            overlap = len(messages) - (len(merged) - len(history))
            if aligned and (not relative_span or
                    (overlap >= relative_span and messages[overlap-relative_span].get('date_label'))):
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
        [(m.get('side'), m.get('time'), m.get('kind'), m.get('text'), m.get('element_id'), m.get('bubble_status'))
         for m in messages[-6:]], ensure_ascii=False).encode()).hexdigest() if messages else None
    context_fingerprint = hashlib.sha256(json.dumps(
        [(m['side'], m['text'], m.get('time'), m.get('kind')) for m in messages], ensure_ascii=False).encode()).hexdigest()
    return {'phone_number': expected, 'contact': contact, 'messages': messages,
            'composer_empty': empty_composer_seen,
            'unclassified': unknown, 'fingerprint': signature,
            'context_fingerprint': context_fingerprint,
            'bounded_complete': bool(stop['reason']), 'stop_reason': stop['reason'] or scanned.reason,
            'source': 'native-current' if not tail and stop['reason'] and not unknown else 'native-foreground',
            'read_mode': 'foreground-bounded', 'history_complete': False}
