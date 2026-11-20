"""Explicit AX receipts only; never infer delivery from transport or body text."""
import re


def parse_status(caption):
    text = (caption or '').strip(' \t\r\n\u200e\u200f')
    known = {
        'Not Delivered': ('delivery', 'not_delivered'), '未送达': ('delivery', 'not_delivered'),
        'Delivered': ('delivery', 'delivered'), '已送达': ('delivery', 'delivered'),
        'Sent as SMS': ('sending_method', 'sms'), '以短信形式发送': ('sending_method', 'sms'),
        'Sent as RCS': ('sending_method', 'rcs'), '以RCS形式发送': ('sending_method', 'rcs'),
        '以 RCS 形式发送': ('sending_method', 'rcs'),
    }
    if text in known:
        field, code = known[text]
        return {field: code, field + '_raw': text}
    match = re.fullmatch(r'(?:Read|已读)(?:\s+((?:[01]?\d|2[0-3]):[0-5]\d(?:\s*[APap][Mm])?))?', text)
    if match:
        return {'delivery': 'read', 'delivery_raw': text, 'read_time': match[1]}
    return None


def update_status(message, status):
    if message.get('side') != 'outgoing':
        return
    current = dict(message.get('bubble_status') or {})
    if 'delivery' in status:
        current.pop('read_time', None)
    current.update(status)
    message['bubble_status'] = current


def attach_checks(checks, messages, *, reverse=False):
    """Associate only consecutive visits, stopping at every unrelated control/gap."""
    by_visit = {}
    for message in messages:
        by_visit.setdefault(message.get('occurrence'), []).append(message)
    previous = None
    target = None
    for check in reversed(checks) if reverse else checks:
        visit = check['occurrence']
        if previous is not None and abs(visit - previous) != 1:
            target = None
        previous = visit
        candidates = by_visit.get(visit, [])
        if candidates:
            target = candidates[0] if len(candidates) == 1 else None
            continue
        caption = check['event'].get('caption', '')
        status = parse_status(caption)
        if status and target is not None:
            update_status(target, status)
        elif caption.strip() not in ('Send failure, Button', '发送失败, 按钮'):
            target = None


def enrich_saved(value):
    """Recover receipts from retained passes, requiring a unique full bubble match."""
    def key(message):
        return tuple(message.get(field) for field in ('element_id', 'side', 'text', 'time', 'kind'))
    targets = {}
    for message in value.get('messages', []):
        targets.setdefault(key(message), []).append(message)
    for result in (value.get('traversal') or {}).get('rounds', []):
        messages = result.get('messages', [])
        attach_checks(result.get('node_checks', []), messages,
                      reverse=result.get('summary', {}).get('direction') == 'up')
        for message in messages:
            matches = targets.get(key(message), [])
            if message.get('element_id') and len(matches) == 1 and message.get('bubble_status'):
                update_status(matches[0], message['bubble_status'])
