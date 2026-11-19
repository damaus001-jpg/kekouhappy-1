"""Read one AX pass in a verified SMS conversation. No ledger or input actions."""
import asyncio
import re
from datetime import datetime
import time

from pymobiledevice3.services.accessibilityaudit import Direction
from ax_recheck import EMPTY_COMPOSERS, IntervalBudget, PathTransitions, message_key, revisit_context
from bubble_records import date_separator
from native_foreground import title_number


TOP_MARKERS = {'Text Message', 'Text Message • SMS', 'Text Message • MMS', 'iMessage \ufffc Encrypted'}
UP_QUIET_SECONDS = .160
DOWN_QUIET_SECONDS = .210
TARGET_SECONDS = 70
FINISH_RESERVE_SECONDS = 10


def delivery_receipt(caption):
    text = caption.strip(' \u200e\u200f')
    return text == 'Delivered' or bool(re.fullmatch(r'Read (?:[01]?\d|2[0-3]):[0-5]\d(?:\s*[AP]M)?', text))


def focus_row(item):
    try:
        identifier = getattr(item, 'platform_identifier', None)
    except KeyError:
        identifier = None  # Save photo can omit PlatformElementValue_v1.
    return {'caption': item.caption or '', 'platform_identifier': identifier,
            'spoken_description': getattr(item, 'spoken_description', None)}


def clock_minutes(value):
    if not value:
        return None
    for fmt in ('%H:%M', '%I:%M%p'):
        try:
            clock = datetime.strptime(value.replace(' ', '').upper(), fmt)
            return clock.hour * 60 + clock.minute
        except ValueError:
            continue
    return None


async def read_pass(*, reverse, phone_number, bottom, move, inspect, deadline, record=None, history=None):
    """move(direction) returns an acknowledged focus; inspect(item, deadline=...) logs a visit.

    Caller checks conversation identity before starting, owns both passes and
    restores the bottom on exit. A downward pass continues from the verified top.
    """
    started = time.monotonic()
    deadline = min(deadline, started + 50)
    rows, checks, intervals, messages = [], [], [], []
    date_breaks = set()
    transitions, budget = PathTransitions(), IntervalBudget()
    step = Direction.Previous if reverse else Direction.Next
    opposite = Direction.Next if reverse else Direction.Previous
    reason, marker, previous = 'time_limit', None, None
    anchor_seen = False
    batch_texts = 0

    async def revisit(item, initial, anomaly, previous_messages):
        probes = []
        expected_path = None
        if len(previous_messages) >= 2:
            a, b = previous_messages[-2:]
            start, end = a['occurrence'], b['occurrence']
            between = [c for c in checks if start < c['occurrence'] < end]
            if between:
                path = [a]
                for check in between:
                    caption = check['event']['caption']
                    if (check['status'] == 'partial' and caption.startswith('Message, ')
                            and caption not in EMPTY_COMPOSERS):
                        path.append({'text': caption[len('Message, '):], 'kind': 'text'})
                    elif check['status'] != 'unclassified':
                        break
                else:
                    expected_path = path + [b]

        async def advance(forward, probe_deadline):
            nonlocal item
            direction = step if forward else opposite
            item = await move(direction)
            row = focus_row(item)
            other_number = title_number(row['caption'])
            if other_number and other_number != phone_number:
                raise ConversationChanged()
            checked = await inspect(item, deadline=min(deadline, probe_deadline))
            probes.append({'direction': direction.name, 'row': row, 'check': checked})
            if row['caption'] in EMPTY_COMPOSERS or other_number or row['caption'].strip() in TOP_MARKERS:
                raise PassBoundary()
            if checked['status'] == 'complete':
                return checked['messages']
            caption = row['caption']
            if expected_path and checked['status'] == 'partial' and caption.startswith('Message, '):
                return [{'text': caption[len('Message, '):], 'kind': 'text'}]
            return []

        try:
            entry = await revisit_context(previous_messages, initial, advance, budget, expected_path=expected_path)
        except PassBoundary:
            entry = {'resolved': False, 'status': 'conversation_boundary',
                     'moves': len(probes), 'boundary_reached': True}
        entry.update(reason=anomaly, probes=probes)
        intervals.append(entry)
        if record:
            record('interval_check', check=entry)
        return item, entry

    try:
        async with asyncio.timeout(max(0, deadline - started)):
            item = await move(Direction.Last if reverse else step)
            while len(rows) < 700:
                row = focus_row(item)
                caption = row['caption']
                rows.append(row)
                number = title_number(caption)
                if number and number != phone_number:
                    raise ConversationChanged()
                checked = await inspect(item, deadline=deadline)
                checks.append(checked)
                if caption.strip() in TOP_MARKERS:
                    marker = len(rows)
                if reverse and marker is not None and number == phone_number and 1 <= len(rows)-marker <= 3:
                    reason = 'top_within_three'
                    break
                if date_separator(caption):
                    previous = None
                current = checked['messages'] if checked['status'] == 'complete' else []
                if any(m.get('text') == bottom.get('text') for m in current):
                    anchor_seen = True
                anomaly = None
                if current and previous is not None:
                    before, after = previous, clock_minutes(current[0].get('time'))
                    if after is not None:
                        delta = (after - before) if reverse else (before - after)
                        if 0 < delta < 180:
                            anomaly = 'suspected_clock_reversal'
                focus_key = (caption, tuple(message_key(m) for m in current))
                prior_focus = transitions.previous
                visits = transitions.observe(focus_key)
                # A run of images or repeated identical messages can be real.
                # Generic controls and attachments cannot establish a loop.
                if (visits >= 3 and current and current[0]['kind'] == 'text'
                        and prior_focus and prior_focus[1] and prior_focus[1] != focus_key[1]):
                    anomaly = 'repeated_path'
                if not reverse and (caption in EMPTY_COMPOSERS or caption == 'add, Button'):
                    if messages and anchor_seen:
                        reason = 'bottom_confirmed'
                        break
                    anomaly = 'composer_without_latest_anchor'
                if anomaly:
                    # Keep this observation before a revisit changes the focus.
                    # Probe evidence has its own ordered path and cannot replace it.
                    messages.extend({**m, 'occurrence': checked['occurrence'], 'source': checked['source']}
                                    for m in current)
                    date_breaks.add(len(checks)-1)
                    if record:
                        record('interval_suspected', reason=anomaly, index=len(rows)-1)
                    context_before = messages[:-len(current)] if current else messages
                    item, interval = await revisit(item, current, anomaly, context_before)
                    previous = marker = None
                    if interval.get('boundary_reached'):
                        reason = 'interval_boundary_unconfirmed'
                        break
                    if interval.get('navigation_uncertain'):
                        reason = 'interval_navigation_uncertain'
                        break
                    if interval['probes']:
                        continue
                    if anomaly == 'composer_without_latest_anchor':
                        reason = 'bottom_anchor_missing'
                        break
                    if anomaly == 'repeated_path' and visits >= 5:
                        reason = 'repeated_transition'
                        break
                if not anomaly:
                    messages.extend({**m, 'occurrence': checked['occurrence'], 'source': checked['source']}
                                    for m in current)
                if current:
                    previous = clock_minutes(current[-1].get('time'))
                    batch_texts += sum(m.get('kind') == 'text' for m in current)
                if reverse and history and batch_texts >= 3:
                    from message_ledger import append_verified_window
                    _, overlap = append_verified_window(history, list(reversed(messages)))
                    batch_texts = 0
                    if overlap:
                        reason = 'history_overlap_verified'
                        break
                item = await move(step)
            else:
                reason = 'element_limit'
    except ConversationChanged:
        reason = 'conversation_changed'
    except TimeoutError:
        reason = 'time_limit' if time.monotonic() >= deadline else 'event_timeout'
    # A separator belongs to the following bubbles in display order, even
    # when it was encountered *after* those bubbles while moving upward.
    dates = {}
    context = None
    prior_index = None
    order = reversed(range(len(checks))) if reverse else range(len(checks))
    for index in order:
        check = checks[index]
        caption = check['event']['caption']
        if prior_index is not None and (
                max(index, prior_index) in date_breaks or
                abs(check['occurrence'] - checks[prior_index]['occurrence']) != 1):
            context = None
        prior_index = index
        if caption in EMPTY_COMPOSERS or caption.strip() in TOP_MARKERS or title_number(caption):
            context = None
        elif separator := date_separator(caption):
            context = separator
        elif context and check['status'] in ('complete', 'partial', 'conflict'):
            check['date_context'] = context
            dates[check['occurrence']] = context
    for message in messages:
        message.update(dates.get(message['occurrence'], {}))
    summary = {'direction': 'up' if reverse else 'down', 'seconds': round(time.monotonic()-started, 2),
               'reason': reason, 'elements': len(rows), 'history_complete': False,
               'distinct_timed_keys': len({message_key(m) for m in messages}),
               'timed_occurrences': len(messages), 'partial_nodes': sum(c['needs_recheck'] for c in checks),
               'label_completed_nodes': sum(c['source'] == 'stable_label' for c in checks),
               'interval_attempts': budget.attempts, 'interval_seconds': round(budget.used_seconds, 3),
               'unresolved_intervals': sum(not i['resolved'] for i in intervals)}
    return {'summary': summary, 'rows': rows, 'node_checks': checks, 'interval_checks': intervals,
            'messages': messages[::-1] if reverse else messages, 'probes': []}


class ConversationChanged(Exception):
    """A different phone title was observed while collecting a pass."""


class PassBoundary(Exception):
    """A local revisit reached the composer, title or start-of-conversation marker."""
