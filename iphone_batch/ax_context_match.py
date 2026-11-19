"""Align recorded observations within one two-pass AX session. No device I/O."""
from collections import Counter, defaultdict

from ax_recheck import EMPTY_COMPOSERS, complete, message_key


def _message(check):
    messages = check['messages']
    if check['status'] == 'complete' and len(messages) == 1 and complete(messages[0]):
        return messages[0]
    return None


def _body(check):
    caption = check['event']['caption']
    spoken = check['event'].get('spoken_description')
    acceptable = (check['status'] == 'partial' or
                  (check['status'] == 'conflict' and 'label_conflicts_with_event' in check.get('reasons', [])
                   and 'caption_spoken_conflict' not in check.get('reasons', [])))
    if (not acceptable or check['messages'] or caption in EMPTY_COMPOSERS
            or (spoken and spoken != caption) or not caption.startswith('Message, ')):
        return None
    body = caption[len('Message, '):]
    if not body.strip() or body in ('Button', 'Image', 'Button, Image', 'Image, Button'):
        return None
    return body


def _same_body(body, message):
    if body == message['text']:
        return True
    traits = message.get('traits') or []
    return bool(traits) and body == message['text'] + ', ' + ', '.join(traits)


def _segments(rounds):
    """Keep probe turns and gaps in the main path as hard boundaries."""
    for result in rounds:
        direction = result['summary']['direction']
        runs = [(direction, direction, result['node_checks'])]
        for number, interval in enumerate(result['interval_checks']):
            probes = interval.get('probes', [])
            current, steps = None, []
            for probe in probes:
                travel = {'Previous': 'up', 'Next': 'down'}[probe['direction']]
                if travel != current:
                    steps = []
                    runs.append((f'{direction}/probe{number}', travel, steps))
                    current = travel
                steps.append(probe['check'])
        for path, travel, checks in runs:
            start = 0
            for end in range(1, len(checks) + 1):
                if end == len(checks) or checks[end]['occurrence'] != checks[end-1]['occurrence'] + 1:
                    segment = checks[start:end]
                    yield path, segment[::-1] if travel == 'up' else segment
                    start = end


def match_context(rounds):
    """Return field updates by occurrence, scoped to one verified conversation.

    Only consider consecutive AX observations. Both neighbors must be distinct
    complete records and unique in their segment. Never add a probe to the
    timeline or borrow a timestamp from a neighboring message.
    """
    if [r['summary']['direction'] for r in rounds] != ['up', 'down']:
        raise ValueError('Expected one up/down pair from the same session')
    if any(r['summary'].get('reason') == 'conversation_changed' for r in rounds):
        raise ValueError('Conversation changed during observation')
    paths = []
    targets = []
    for path, segment in _segments(rounds):
        messages = [_message(check) for check in segment]
        keys = [message_key(m) if m else None for m in messages]
        positions = defaultdict(list)
        for index, key in enumerate(keys):
            if key:
                positions[key].append(index)
        paths.append((path, segment, messages, positions))
        for i in range(1, len(segment) - 1):
            left, right = keys[i-1], keys[i+1]
            if not left or not right or left == right:
                continue
            check = segment[i]
            pair = left, right
            body = _body(check)
            if (path in ('up', 'down') and body and
                    len(positions[left]) == len(positions[right]) == 1):
                targets.append((path, check, pair, body))

    updates = []
    for path, target, pair, body in targets:
        witnesses = []
        for other, segment, messages, positions in paths:
            if other == path:
                continue
            left, right = (positions.get(key, []) for key in pair)
            if not left or not right:
                continue
            if len(left) != 1 or len(right) != 1 or right[0] != left[0] + 2:
                break
            middle = left[0] + 1
            check, message = segment[middle], messages[middle]
            if not message and _body(check) == body:
                continue
            if not message or message['kind'] != 'text' or not _same_body(body, message):
                break
            witnesses.append((check['occurrence'], message))
        else:
            if witnesses and len({message_key(m) for _, m in witnesses}) == 1:
                m = witnesses[0][1]
                updates.append({'occurrence': target['occurrence'], 'path': path,
                                'side': m['side'], 'time': m['time'], 'text': m['text'],
                                'kind': 'text', 'source': 'matched_ax_context',
                                **target.get('date_context', {}),
                                'witness_occurrences': [n for n, _ in witnesses],
                                'neighbors': pair})
    # Two separate target visits can look identical. One source observation
    # cannot establish the identities of both.
    claims = Counter(n for update in updates for n in update['witness_occurrences'])
    return [update for update in updates if
            all(claims[n] == 1 for n in update['witness_occurrences'])]
