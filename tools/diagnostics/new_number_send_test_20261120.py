"""Exactly three user-authorized test messages on device 01; never retry a send."""
import argparse
import asyncio
import json
from pathlib import Path
import random
import re
import sys
import time
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'iphone_batch'))
from native_workspace import ROOT, raw_page, prepared_send_control
from native_conversation import NativeConversation, phone_key
from native_message_page import read_message_footer
from native_ui_scan import scan
from pairing_patch import open_paired_usb
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from workspace_access import signed_opener
from message_ledger import MessageLedger
from message_archive import conversations

OUT = ROOT / 'diagnostics' / 'new-number-test-20261120'
BODIES = ['Hey old man', 'Are u free\uff1f', 'Are you free\uff1f']


def emit(stage, **values):
    print(json.dumps({'stage': stage, **values}, ensure_ascii=True), flush=True)


def state():
    with signed_opener().open('http://127.0.0.1:8070/api/state', timeout=8) as response:
        result = json.load(response)
    device = next(row for row in result['devices'] if row.get('number') == '01')
    if (not device.get('ready') or device.get('readonly') or
            result.get('active') != device['udid'] or
            result.get('selected', result.get('active')) != device['udid']):
        raise RuntimeError('Device 01 must remain selected, ready and controllable')
    return device


def save(index, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f'{index}.json'
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def archive_sent(record):
    device, number = record['device'], record['phone_number']
    identifier = 'new-number-test-20261120-' + str(record['index'])
    ledger = MessageLedger(ROOT)
    previous = ledger.load(device, number)
    if previous:
        history = previous['messages']
    else:
        saved = next((c for c in conversations(device, ROOT/'diagnostics') if c.get('phone_number') == number), None)
        history = saved['messages'] if saved else []
    caption = record['outgoing'][0]
    observed_time = re.search(r', (\d{1,2}:\d{2})(?:,|$)', caption)
    message = {'side':'outgoing', 'text':record['text'], 'kind':'text',
               'time':observed_time.group(1) if observed_time else record['requested_at'],
               'message_id':device+':send:'+identifier, 'record_source':'native-send',
               'confirmed_send_id':identifier, 'sent_at':record['requested_at']}
    if not any(m.get('message_id') == message['message_id'] for m in history):
        history = [*history, message]
    output = ROOT/'diagnostics'/('sms-'+identifier+'-reading.json')
    saved = ledger.commit(device, number, history, [message], True,
                          previous.get('snapshot') if previous else None,
                          previous.get('pending_windows') if previous else None,
                          baseline_complete=bool(previous and previous.get('baseline_complete')),
                          conversation_id=output.stem)
    value = {'device':device, 'contact':number, 'phone_number':number,
             'created':record['verified_at'], 'source':'saved', 'messages':saved['messages'],
             'history_complete':False, 'baseline_complete':saved['baseline_complete'],
             'scope':'\u5df2\u540c\u6b65\u624b\u673a\u786e\u8ba4\u53d1\u9001\u7684\u6d4b\u8bd5\u77ed\u4fe1\uff1b\u5b8c\u6574\u5386\u53f2\u5f85\u6838\u5bf9'}
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    record['conversation_id'] = output.stem
    record['reading_archived'] = True
    save(record['index'], record)
    emit('reading_archived', index=record['index'], phone=number, conversation_id=output.stem)


async def recipient(service, number):
    def matches(item):
        caption = item.caption or ''
        return ', Button' in caption and any(phone_key(part) == number for part in caption.split(', '))
    result = await scan(service, limit=12, seconds=5, settle=0, stop_when=matches)
    if not any(matches(item) for item in result):
        raise RuntimeError('Exact committed recipient not confirmed; no send')


async def ensure_list(service, phone):
    footer = await read_message_footer(service)
    emit('page_identified', page=footer['page_type'], input=footer['input_state'])
    if footer['page_type'] == 'conversation':
        if footer['input_state'] != 'empty':
            raise RuntimeError('Existing phone draft preserved; no navigation or send')
        try:
            for step in range(19):
                x = round((.015 + (.78 - .015) * step / 18) * 65535)
                phone.request(phone.base, '/touch', {'type': 'contact', 'x': x, 'y': 32768})
                await asyncio.sleep(.025)
        finally:
            phone.request(phone.base, '/touch', {'type': 'release', 'x': round(.78 * 65535), 'y': 32768})
        await asyncio.sleep(.3)
        footer = await read_message_footer(service)
    if footer['page_type'] != 'message_list' or not footer['compose_available']:
        raise RuntimeError('Messages list with Compose not confirmed; no new message')


async def prepare(service, phone, index, number, text):
    path = OUT / f'{index}.json'
    if path.exists():
        raise RuntimeError(f'Test record {index} already exists; no automatic repeat')
    state()
    await ensure_list(service, phone)
    await phone.chord(0x11)
    await asyncio.sleep(.25)
    rows = await raw_page(service)
    captions = [row['caption'] for row in rows]
    if ('To:' not in captions or 'Message' not in captions or not any(
            caption.startswith('New Message, Show Conversation Details') for caption in captions)):
        raise RuntimeError('Blank new message not confirmed; no number entered')
    await phone.paste(number)
    await asyncio.sleep(.25)
    captions = [row['caption'] for row in await raw_page(service)]
    if not any(caption.startswith('To:, ') and phone_key(caption[5:]) == number for caption in captions):
        raise RuntimeError('Recipient input mismatch; no Return or send')
    await phone.keys([0x28]); await phone.keys([])
    await asyncio.sleep(.35)
    await recipient(service, number)
    footer = await read_message_footer(service)
    if footer['page_type'] != 'conversation' or footer['input_state'] != 'empty':
        raise RuntimeError('New recipient composer is not empty; existing draft preserved')
    # The existing verified native workflow uses Tab from the committed
    # recipient to the body. No screenshot or coordinate guess is required.
    await phone.keys([0x2B]); await phone.keys([])
    await phone.paste(text)
    await asyncio.sleep(.25)
    await recipient(service, number)
    footer = await read_message_footer(service)
    prepared_send_control({'phone_number': number, 'raw_elements': footer['raw_elements']}, number, text)
    record = {'index': index, 'device': state()['udid'], 'phone_number': number,
              'text': text, 'status': 'prepared_verified', 'prepared_at': datetime.now(timezone.utc).isoformat()}
    save(index, record)
    emit('prepared_verified', index=index, phone=number, text=text)
    return record


async def send_prepared(service, phone, record, deadline=None):
    index, number, text = record['index'], record['phone_number'], record['text']
    if record['status'] != 'prepared_verified':
        raise RuntimeError('Record is not a verified unsent preparation')
    if deadline is not None:
        remaining = deadline - time.monotonic() - 2
        if remaining > 0:
            emit('spacing_wait', seconds=round(remaining, 3))
            await asyncio.sleep(remaining)
    state()
    await recipient(service, number)
    footer = await read_message_footer(service)
    prepared_send_control({'phone_number': number, 'raw_elements': footer['raw_elements']}, number, text)
    if deadline is not None and time.monotonic() < deadline:
        await asyncio.sleep(deadline-time.monotonic())
    # Persist before the one Return press. Any exception after this marker
    # is uncertain and must never cause an automatic resend.
    sent_clock = time.monotonic()
    record.update(status='send_requested', requested_at=datetime.now(timezone.utc).isoformat())
    save(index, record)
    await phone.keys([0x28]); await phone.keys([])
    emit('send_requested', index=index, phone=number, text=text)
    await asyncio.sleep(.7)
    outgoing = re.compile(r'^Your (?:iMessage|Message|SMS|Text Message), ' + re.escape(text) + r', \d{1,2}:\d{2}(?:,|$)')
    found = []
    for attempt in range(3):
        await recipient(service, number)
        rows = await scan(service, limit=14, seconds=4, settle=0, reverse=True,
                          stop_when=lambda item: bool(outgoing.search(item.caption or '')))
        found = [item.caption for item in rows if outgoing.search(item.caption or '')]
        footer = await read_message_footer(service)
        if found and footer['input_state'] == 'empty':
            break
        if attempt < 2:
            await asyncio.sleep(.4)
    if not found or footer['input_state'] != 'empty':
        raise RuntimeError('Send result uncertain; stopped without retrying')
    record.update(status='sent_verified', verified_at=datetime.now(timezone.utc).isoformat(), outgoing=found)
    save(index, record)
    emit('sent_verified', index=index, phone=number, text=text)
    archive_sent(record)
    return sent_clock


async def main(mode, numbers_file):
    source = Path(numbers_file).resolve()
    numbers = [phone_key(row.strip()) for row in source.read_text(encoding='utf-8-sig').splitlines() if row.strip()][:3]
    if len(numbers) != 3 or None in numbers or len(set(numbers)) != 3:
        raise RuntimeError('Exactly three distinct valid test numbers are required')
    device = state(); phone = NativeConversation(); phone.base = f"http://127.0.0.1:{device['port']}"
    lockdown = await open_paired_usb(device['udid'], ROOT)
    try:
        async with AccessibilityAudit(lockdown) as service:
            if mode == 'prepare-first':
                await prepare(service, phone, 1, numbers[0], BODIES[0])
                return
            record = json.loads((OUT / '1.json').read_text(encoding='utf-8'))
            if record.get('phone_number') != numbers[0] or record.get('text') != BODIES[0]:
                raise RuntimeError('First preparation does not match this exact authorized test')
            previous = await send_prepared(service, phone, record)
            for index in (2, 3):
                gap = random.uniform(15, 25)
                deadline = previous + gap
                emit('next_spacing', next_index=index, target_seconds=round(gap, 3))
                record = await prepare(service, phone, index, numbers[index - 1], BODIES[index - 1])
                prior = previous
                previous = await send_prepared(service, phone, record, deadline)
                record['interval_seconds'] = round(previous - prior, 3)
                record['target_interval_seconds'] = round(gap, 3)
                save(index, record)
                emit('actual_spacing', index=index, seconds=record['interval_seconds'])
    finally:
        await lockdown.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['prepare-first', 'send-three'])
    parser.add_argument('--numbers-file', required=True, help='Private TXT containing the three intended test recipients first; send-three sends real messages.')
    args = parser.parse_args()
    try:
        asyncio.run(main(args.mode, args.numbers_file))
    except Exception as error:
        emit('stopped', error=str(error))
        sys.exit(1)
