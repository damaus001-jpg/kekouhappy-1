"""Verify a message body followed by a composer edge using AX observations."""
import asyncio
import time
from pymobiledevice3.services.accessibilityaudit import Direction, deserialize_object
from ax_recheck import EMPTY_COMPOSERS
from ax_traversal import delivery_receipt, focus_row


def bottom_control(caption):
    return caption in EMPTY_COMPOSERS or caption == 'add, Button'


async def move_focus(service, direction, quiet=.08):
    """Send one focus move and consume its settled acknowledgement."""
    async def receive(timeout):
        async with asyncio.timeout(timeout):
            while True:
                name, args = await service._event_queue.get()
                if name == 'hostInspectorCurrentElementChanged:':
                    data = deserialize_object(service._extract_event_payload(args))
                    items = data if isinstance(data, list) else [data]
                    if items:
                        return items[0]
    if hasattr(service, 'set_show_visuals'):
        await service.set_show_visuals(False)
    while not service._event_queue.empty():
        service._event_queue.get_nowait()
    await service.move_focus(direction)
    item = await receive(1)
    deadline = time.monotonic()+.4
    while time.monotonic()<deadline:
        try:
            item = await receive(min(quiet,max(.001,deadline-time.monotonic())))
        except TimeoutError:
            break
    return item


async def reach_bottom(*, move, inspect, deadline, anchor=None, max_steps=240):
    """Find the anchor upward, then read forward to +/composer, including arrivals.

    With no anchor, establish the nearest message before the composer edge.
    The caller owns the time budget and conversation identity checks.
    """
    checks, messages = [], []
    item = await move(Direction.Last)
    edge = False
    matched = False
    newest = None
    phase = 'seek_anchor' if anchor else 'seek_edge'
    for _ in range(max_steps):
        row = focus_row(item)
        caption = row['caption']
        check = await inspect(item, deadline=deadline)
        checks.append(check)
        current = check['messages'] if check['status'] == 'complete' else []
        if phase == 'forward':
            if current:
                messages.extend(current)
                newest = current[-1]
            if bottom_control(caption):
                return {'confirmed': matched, 'anchor': anchor, 'latest': newest,
                        'messages': messages, 'checks': checks, 'control': caption}
            item = await move(Direction.Next)
            continue
        if bottom_control(caption):
            edge = True
            if phase == 'seek_edge':
                phase = 'seek_nearest'
        elif caption.startswith('Send, Button'):
            raise ValueError('手机输入框已有草稿，请先处理后再读取')
        elif caption.startswith('Message, ') and not edge:
            raise ValueError('手机输入框已有草稿，请先处理后再读取')
        elif current:
            candidate = current[-1]
            if (anchor and candidate.get('text') == anchor.get('text')) or (
                    not anchor and phase == 'seek_nearest'):
                anchor = anchor or candidate
                newest = candidate
                messages.append(candidate)
                matched = True
                phase = 'forward'
                item = await move(Direction.Next)
                continue
        elif phase == 'seek_nearest' and not (
                delivery_receipt(caption) or caption.startswith('Record audio, Button')):
            # The immediate message is partial. Do not substitute an older one.
            if check.get('needs_recheck'):
                return {'confirmed': False, 'anchor': anchor, 'latest': None,
                        'messages': messages, 'checks': checks, 'reason': 'latest_fields_incomplete'}
        item = await move(Direction.Previous)
    return {'confirmed': False, 'anchor': anchor, 'latest': newest, 'messages': messages,
            'checks': checks, 'reason': 'bottom_step_limit'}
