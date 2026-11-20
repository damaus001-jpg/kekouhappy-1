"""Two-pass AX conversation capture shared by manual and automatic readers."""
import asyncio
import hashlib
import json
import time

from pymobiledevice3.services.accessibilityaudit import Direction, deserialize_object
from ax_context_match import match_context
from ax_bottom import reach_bottom
from ax_recheck import EMPTY_COMPOSERS, inspect_node, message_key
from ax_traversal import delivery_receipt, focus_row, read_pass, UP_QUIET_SECONDS, DOWN_QUIET_SECONDS
from native_foreground import confirmed_title, title_number
from bubble_status import attach_checks
from reading_progress import ReadingProgress, visible_messages


async def capture_conversation(service, options=None):
    options = options or {}
    began = time.monotonic()
    deadline = began + 60
    serial = 0
    rounds, bottom = [], None
    number = contact = None
    changed = cancelled = False
    restored = False
    quiet = UP_QUIET_SECONDS

    async def receive(timeout):
        async with asyncio.timeout(timeout):
            while True:
                name, args = await service._event_queue.get()
                if name != 'hostInspectorCurrentElementChanged:':
                    continue
                data = deserialize_object(service._extract_event_payload(args))
                items = data if isinstance(data, list) else [data]
                if items:
                    return items[0]

    async def move(direction):
        while not service._event_queue.empty():
            service._event_queue.get_nowait()
        await service.move_focus(direction)
        item = await receive(2)
        until = time.monotonic()+.6
        while time.monotonic() < until:
            try:
                item = await receive(min(quiet, max(.001, until-time.monotonic())))
            except TimeoutError:
                break
        other = title_number(item.caption or '')
        if other and other != number:
            raise ChangedConversation()
        return item

    async def inspect(item, *, deadline):
        nonlocal serial
        serial += 1
        checked = await inspect_node(focus_row(item), contact, occurrence=serial,
            query_label=lambda: service.element_attribute(item.element.identifier, 'Label'),
            deadline=deadline)
        if progress is not None and not progress.best:
            progress.publish(visible_messages([checked]))
        return checked

    bottom_checks = []
    finish_messages = []
    progress = None

    def publish_node(event, **data):
        if progress is not None and event == 'node':
            progress.publish(visible_messages(data['checks'], reverse=data['reverse']))

    async def verify_bottom(anchor=None):
        result = await reach_bottom(move=move, inspect=inspect, deadline=deadline, anchor=anchor)
        bottom_checks.append(result)
        if not result['confirmed'] or not result['latest']:
            raise ValueError('底部消息与输入框或加号尚未确认')
        return result

    try:
        async with asyncio.timeout(max(.001, deadline-time.monotonic()-8)):
            title = await confirmed_title(service)
            if not title.get('found'):
                raise ValueError('未确认当前会话手机号')
            number, contact = title['phone_number'], title['contact']
            if options.get('phone_number') and options['phone_number'] != number:
                changed = True
                return {'changed': True, 'phone_number': number}
            progress = ReadingProgress(options.get('device'), number, contact,
                                       callback=options.get('on_progress'))
            await service.set_app_monitoring_enabled(True)
            await service.set_monitored_event_type()
            history = options.get('history') or []
            opening = await verify_bottom(history[-1] if history else None)
            bottom = opening['latest']
            for reverse in (True, False):
                quiet = UP_QUIET_SECONDS if reverse else DOWN_QUIET_SECONDS
                result = await read_pass(reverse=reverse, phone_number=number, bottom=bottom,
                    move=move, inspect=inspect, deadline=deadline-8,
                    record=publish_node,
                    history=history if options.get('allow_overlap_stop', True) else None)
                rounds.append(result)
                if result['summary']['reason'] == 'conversation_changed':
                    changed = True
                    break
                if result['summary']['reason'] not in ('top_within_three', 'focus_cycle_verified', 'bottom_confirmed', 'history_overlap_verified'):
                    break
    except ChangedConversation:
        changed = True
    except asyncio.CancelledError:
        cancelled = True
        raise
    except TimeoutError:
        if not rounds:
            raise ValueError('会话遍览超时，尚未取得可显示记录') from None
    finally:
        try:
            if not cancelled and not changed and number:
                async with asyncio.timeout(max(.001, deadline-time.monotonic())):
                    if rounds and rounds[-1]['summary']['reason'] == 'bottom_confirmed':
                        restored = True
                    else:
                        title = await confirmed_title(service)
                        if title.get('phone_number') == number:
                            await service.set_app_monitoring_enabled(True)
                            await service.set_monitored_event_type()
                            finish = await verify_bottom(bottom)
                            finish_messages.extend(finish['messages'])
                            restored = True
        except (TimeoutError, ValueError, ChangedConversation):
            restored = False
        finally:
            await service.set_app_monitoring_enabled(False)
    if changed:
        return {'changed': True, 'phone_number': number}
    updates = match_context(rounds) if len(rounds) == 2 else []
    enriched = {u['occurrence']: u for u in updates}
    unknown = []
    for result in rounds:
        for check in result['node_checks']:
            if check['occurrence'] in enriched:
                result['messages'].append(enriched[check['occurrence']])
            elif check['needs_recheck']:
                unknown.append(check)
        # Match order follows recorded visits within each pass.
        result['messages'].sort(key=lambda m: m['occurrence'],
                                reverse=result['summary']['direction'] == 'up')
        attach_checks(result['node_checks'], result['messages'],
                      reverse=result['summary']['direction'] == 'up')
    from native_workspace import digest, merge_history_messages
    messages = rounds[0]['messages'] if rounds else []
    aligned = False
    if len(rounds) == 2:
        # A path with a failed revisit is evidence, not an ordered timeline.
        # Keep it in traversal.rounds without importing its repeated visits.
        if not any(r['summary']['unresolved_intervals'] for r in rounds):
            messages, aligned = merge_history_messages(messages, rounds[1]['messages'])
    if finish_messages and restored:
        from message_ledger import append_verified_window
        if messages and messages[-1].get('text') == finish_messages[0].get('text'):
            merged, finish_aligned = messages + finish_messages[1:], True
        else:
            merged, finish_aligned = append_verified_window(messages, finish_messages)
        if finish_aligned:
            messages = merged
        else:
            unknown.append({'reason': 'new_tail_order_unconfirmed', 'messages': finish_messages})
    latest_bottom = bottom
    if restored:
        if finish_messages:
            latest_bottom = finish_messages[-1]
        elif rounds and rounds[-1]['messages']:
            latest_bottom = rounds[-1]['messages'][-1]
    uncertain = (not aligned or not restored or bool(unknown) or any(
        r['summary']['unresolved_intervals'] for r in rounds))
    if uncertain:
        unknown.append({'reason': 'two_pass_order_or_fields_unconfirmed'})
    reading_messages = messages
    if uncertain and rounds:
        reading_messages = visible_messages(rounds[0]['node_checks'], rounds[0]['messages'],
                                            reverse=rounds[0]['summary']['direction'] == 'up') or messages
    if progress is not None:
        progress.publish(reading_messages, phase='complete', final=True)
    for index, message in enumerate(messages, 1):
        message['sequence'] = index
    fingerprint = hashlib.sha256(json.dumps(
        [(m.get('side'), m.get('time'), m.get('kind'), m.get('text'), m.get('element_id'), m.get('bubble_status'))
         for m in messages[-6:]], ensure_ascii=False).encode()).hexdigest()
    return {'phone_number': number, 'contact': contact, 'messages': messages,
            'reading_messages': reading_messages,
            'unclassified': unknown, 'raw_elements': [row for r in rounds for row in r['rows']],
            'fingerprint': fingerprint, 'context_fingerprint': digest(messages),
            'bounded_complete': not uncertain, 'history_complete': False,
            'source': 'native-foreground' if uncertain else 'native-current',
            'read_mode': 'ax-two-pass', 'stop_reason': rounds[-1]['summary']['reason'] if rounds else 'no_pass',
            'bottom_confirmed': restored, 'elapsed_seconds': round(time.monotonic()-began, 3),
            'bottom_anchor': latest_bottom,
            'traversal': {'rounds': rounds, 'context_updates': updates, 'bottom_checks': bottom_checks}}


class ChangedConversation(Exception):
    """Capture must leave the newly selected conversation under user control."""
