"""Distinguish Messages list and conversation using only fixed footer controls."""
from native_ui_scan import scan


EMPTY_COMPOSERS = frozenset(('Message', 'Message, iMessage', 'Message, Text Message',
                             'Message, Text Message, SMS'))


def classify_footer(records):
    captions = [row.get('caption') or '' for row in records]
    compose = 'Compose, Button' in captions
    search = any(caption in ('Search, Search Field', 'Search, Button') for caption in captions)
    add = any(caption in ('add, Button', '+, Button', '＋, Button') for caption in captions)
    inputs = [caption for caption in captions if caption == 'Message' or caption.startswith('Message, ')]
    send = [caption for caption in captions if caption.startswith('Send, Button')]
    audio = any(caption.startswith('Record audio, Button') for caption in captions)
    kind = 'unknown'
    # Reject mixed footer snapshots rather than act on a page transition.
    if search and not add and not inputs and not send and not audio:
        kind = 'message_list'
    elif add and not compose and not search:
        kind = 'conversation'
    return {'page_type': kind,
            'input_state': ('empty' if inputs[0] in EMPTY_COMPOSERS else 'draft')
                           if kind == 'conversation' and len(inputs) == 1 else 'unknown',
            'send_available': kind == 'conversation' and len(inputs) == 1 and
                              inputs[0] not in EMPTY_COMPOSERS and len(send) == 1 and
                              not any(word in send[0] for word in ('Dimmed', 'Disabled')),
            'compose_available': kind == 'message_list' and compose}


async def read_message_footer(service):
    observed = []
    def found(item):
        observed.append({'caption': item.caption or '', 'platform_identifier': item.platform_identifier})
        return classify_footer(observed)['page_type'] != 'unknown'
    result = await scan(service, limit=4, seconds=3, settle=0, reverse=True, stop_when=found)
    records = [{'caption': item.caption or '', 'platform_identifier': item.platform_identifier} for item in result]
    return {**classify_footer(records), 'elements_checked': len(records),
            'scan_seconds': result.elapsed, 'reason': result.reason, 'raw_elements': records}
