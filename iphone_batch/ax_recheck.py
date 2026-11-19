"""Evidence-based AX node checks. No device moves, message writes or activation."""
import asyncio
from collections import Counter
import time

from sms_collect import parse_records

EMPTY_COMPOSERS = {'Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS'}


def message_key(message):
    return tuple(message.get(k) for k in ('side', 'text', 'time', 'kind'))


def parse_caption(caption, contact):
    if not isinstance(caption, str) or not caption:
        return []
    return parse_records([{'caption': contact + ', Show Conversation Details, Button'},
                          {'caption': caption}])[1]


def complete(message):
    return (message.get('side') in ('incoming', 'outgoing') and bool(message.get('time'))
            and message.get('kind') in ('text', 'attachment') and bool(message.get('text')))


def normalized(value):
    return ' '.join((value or '').split())


def compatible(caption, original, candidate):
    if original:
        for name in ('side', 'time', 'text', 'kind'):
            old, new = original.get(name), candidate.get(name)
            if old not in (None, '', 'unknown') and new not in (None, '', 'unknown'):
                if normalized(str(old)) != normalized(str(new)):
                    return False
        return True
    if caption.startswith('Message, '):
        body = caption[len('Message, '):]
        if body in ('Button', 'Button, Image', 'Image', 'Image, Button'):
            return True
        return normalized(body) == normalized(candidate.get('text'))
    return True


async def inspect_node(row, contact, *, occurrence, query_label=None, query_timeout=.6,
                       force=False, deadline=None):
    """Read only the current node; retain occurrences and all conflicting evidence."""
    caption = row.get('caption') or ''
    original = parse_caption(caption, contact)
    for message in original:
        message.update(element_id=row.get('platform_identifier'), occurrence=occurrence,
                       source='caption')
    spoken = row.get('spoken_description') or ''
    spoken_messages = parse_caption(spoken, contact)
    result = {'occurrence': occurrence, 'event': dict(row), 'status': 'unclassified',
              'needs_recheck': False, 'reasons': [], 'messages': original,
              'source': 'caption', 'label_queries': [], 'highlight_coverage': 'unknown',
              'missing_fields': []}
    is_composer = caption in EMPTY_COMPOSERS
    candidate = (bool(original) or bool(spoken_messages) or 'Includes picture' in caption
                 or caption.startswith('Message, ') or caption == 'Image') and not is_composer
    if not candidate:
        return result
    result.update(status='partial', needs_recheck=True)
    if not original:
        result['missing_fields'] = ['direction', 'time']
        if caption in ('Message, Button', 'Message, Button, Image'):
            result['missing_fields'].append('body_or_attachment')
    else:
        result['missing_fields'] = [name for name, field in (
            ('direction', 'side'), ('time', 'time'), ('body_or_attachment', 'text'))
            if not original[0].get(field) or original[0].get(field) == 'unknown']
    if original and all(complete(m) for m in original):
        result.update(status='complete', needs_recheck=False)
    elif original:
        result['reasons'].append('incomplete_metadata')
    else:
        result['reasons'].append('message_node_without_complete_record')
    if spoken_messages and original and [message_key(m) for m in spoken_messages] != [message_key(m) for m in original]:
        result.update(status='conflict', needs_recheck=True)
        result['reasons'].append('caption_spoken_conflict')
    if not result['needs_recheck'] and not force:
        return result
    if query_label is None:
        return result
    for attempt in (1, 2):
        remaining = query_timeout if deadline is None else min(query_timeout, deadline - time.monotonic())
        if remaining <= 0:
            result['reasons'].append('query_budget_exhausted')
            return result
        began = time.monotonic()
        evidence = {'attempt': attempt}
        try:
            label = await asyncio.wait_for(query_label(), remaining)
            evidence['value'] = label if isinstance(label, str) else None
            if label is not None and not isinstance(label, str):
                evidence['unexpected_type'] = type(label).__name__
        except Exception as error:
            evidence.update(value=None, error=type(error).__name__, detail=str(error))
        evidence['seconds'] = round(time.monotonic() - began, 4)
        result['label_queries'].append(evidence)
    first, second = (q.get('value') for q in result['label_queries'])
    if not first or not second:
        result['reasons'].append('label_unavailable')
        return result
    if first != second:
        result.update(status='conflict', needs_recheck=True)
        result['reasons'].append('label_changed_between_queries')
        return result
    parsed = parse_caption(first, contact)
    if not parsed or not all(complete(m) for m in parsed):
        result['reasons'].append('label_did_not_complete_record')
        return result
    if len(parsed) != 1 or not compatible(caption, original[0] if original else None, parsed[0]):
        result.update(status='conflict', needs_recheck=True)
        result['reasons'].append('label_conflicts_with_event')
        return result
    if result['status'] == 'conflict':
        return result
    for message in parsed:
        message.update(element_id=row.get('platform_identifier'), occurrence=occurrence,
                       source='stable_label')
    result.update(status='complete', needs_recheck=False, messages=parsed, source='stable_label')
    result['missing_fields'] = []
    result['reasons'].append('completed_by_two_equal_label_reads')
    return result


class IntervalBudget:
    """A pass may spend at most two attempts and twelve seconds revisiting gaps."""
    def __init__(self, max_attempts=2, seconds=12, clock=time.monotonic):
        self.max_attempts, self.seconds, self.clock = max_attempts, seconds, clock
        self.attempts, self.used_seconds = 0, 0.0

    def begin(self):
        if self.attempts >= self.max_attempts or self.used_seconds >= self.seconds:
            return None
        self.attempts += 1
        return self.clock() + self.seconds - self.used_seconds

    def finish(self, started):
        self.used_seconds += max(0, self.clock() - started)


def unique_tail_pair(messages):
    """Use an ordered pair, never an element ID or one matching repeated body."""
    keys = [message_key(m) for m in messages if complete(m)]
    if len(keys) < 2 or keys[-1] == keys[-2]:
        return None
    pair = tuple(keys[-2:])
    counts = Counter(zip(keys, keys[1:]))
    return pair if counts[pair] == 1 else None


class PathTransitions:
    """Count the transition just observed, not an unrelated historical maximum."""
    def __init__(self):
        self.previous = None
        self.counts = Counter()

    def observe(self, key):
        edge = (self.previous, key)
        self.counts[edge] += 1
        self.previous = key
        return self.counts[edge]


async def revisit_context(previous_messages, initial_messages, advance, budget, *, expected_path=None):
    """Reacquire ordered context within 12 acknowledged moves and a shared budget.

    advance(forward, deadline) returns messages from the newly focused node.
    Reacquiring context proves position only, never whole-history completeness.
    """
    pair = unique_tail_pair(previous_messages[-10:])
    result = {'resolved': False, 'anchor_pair': pair, 'status': 'no_unique_context_pair',
              'moves': 0}
    if pair is None:
        return result
    deadline = budget.begin()
    if deadline is None:
        result['status'] = 'interval_budget_exhausted'
        return result
    began = budget.clock()
    result['attempt'] = budget.attempts

    async def move(forward):
        result['moves'] += 1
        return await advance(forward, deadline)

    last = message_key(initial_messages[-1]) if initial_messages else None
    path = expected_path or []
    observed = list(initial_messages)

    def path_matches():
        if len(observed) < len(path):
            return False
        for expected, actual in zip(path, observed[-len(path):]):
            if expected.get('text') != actual.get('text'):
                return False
            for field in ('side', 'time', 'kind'):
                before, after = expected.get(field), actual.get(field)
                if before and after and before != after:
                    return False
        # At least the first anchor must have complete identity evidence.
        return complete(observed[-len(path)])

    try:
        async with asyncio.timeout(max(.001, deadline - budget.clock())):
            for _ in range(6):
                for message in await move(True):
                    if path:
                        observed.append(message)
                        observed = observed[-len(path):]
                        if path_matches():
                            full = complete(message)
                            result.update(resolved=full, position_reacquired=True,
                                status='forward_ordered_path_revisited' if full else 'forward_body_context_revisited')
                            return result
                        continue
                    key = message_key(message)
                    if last == pair[0] and key == pair[1]:
                        result.update(resolved=True, status='forward_ordered_pair_revisited')
                        return result
                    last = key
            if path:
                result['status'] = 'ordered_path_not_reacquired'
                return result
            last, found = None, False
            for _ in range(4):
                for message in await move(False):
                    key = message_key(message)
                    if last == pair[1] and key == pair[0]:
                        found = True
                        break
                    last = key
                if found:
                    break
            if not found:
                result['status'] = 'anchor_pair_not_reacquired'
                return result
            result['status'] = 'frontier_not_reacquired'
            for _ in range(2):
                messages = await move(True)
                if not messages:
                    continue
                if message_key(messages[0]) == pair[1]:
                    result.update(resolved=True, status='ordered_pair_revisited')
                else:
                    result['status'] = 'unexpected_text_between_context_pair'
                break
    except TimeoutError:
        result.update(status='interval_timeout', navigation_uncertain=True)
    finally:
        budget.finish(began)
        result['seconds'] = round(budget.clock() - began, 3)
    return result
