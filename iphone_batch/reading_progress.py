"""Publish observed text before traversal verification or bottom restoration."""
from copy import deepcopy
import json
from pathlib import Path
import re
import time
import uuid

from bubble_records import date_separator
from bubble_status import attach_checks

EMPTY = {'Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS'}
ROOT = Path(__file__).resolve().parent / '.device-data'


def visible_messages(checks, messages=None, *, reverse=False):
    known = {}
    for message in messages or []:
        known.setdefault(message.get('occurrence'), []).append(message)
    rows, date = [], {}
    for check in reversed(checks) if reverse else checks:
        caption = check['event'].get('caption', '')
        separator = date_separator(caption)
        if separator:
            date = separator
        parsed = known.get(check['occurrence'], check.get('messages') or [])
        if not parsed and caption.startswith('Message, ') and caption not in EMPTY:
            text = caption[len('Message, '):]
            if text not in ('Button', 'Image', 'Button, Image', 'Image, Button'):
                parsed = [{'side': 'unknown', 'text': text, 'time': None, 'kind': 'text',
                           'reading_pending': True, 'occurrence': check['occurrence'],
                           'element_id': check['event'].get('platform_identifier')}]
        for message in parsed:
            row = {**date, **deepcopy(message)}
            row.setdefault('occurrence', check['occurrence'])
            rows.append(row)
    attach_checks(checks, rows, reverse=reverse)
    for index, row in enumerate(rows, 1):
        row['sequence'] = index
    return rows


def progress_path(root, device):
    if not isinstance(device, str) or not re.fullmatch(r'[A-Za-z0-9_-]{4,80}', device):
        raise ValueError('读取进度设备无效')
    return Path(root) / 'workspace' / 'reading-progress' / (device + '.json')


def load_progress(device, root=ROOT):
    try:
        value = json.loads(progress_path(root, device).read_text(encoding='utf-8'))
        if value.get('device') == device and 0 <= time.time() * 1000 - value['updated_at'] < 180000:
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


class ReadingProgress:
    def __init__(self, device, number, contact, *, root=ROOT, callback=None):
        self.device, self.number, self.contact = device, number, contact
        self.root, self.callback = root, callback
        self.read_id, self.revision = uuid.uuid4().hex, 0
        self.best, self.signature = [], None

    def publish(self, rows, *, phase='reading', final=False):
        # A short downward revisit must not hide the longer upward window.
        if not final and len(rows) < len(self.best):
            return
        signature = json.dumps(rows, ensure_ascii=False, sort_keys=True)
        if signature == self.signature and not final:
            return
        self.best, self.signature = deepcopy(rows), signature
        self.revision += 1
        value = {'read_id': self.read_id, 'revision': self.revision, 'device': self.device,
                 'phone_number': self.number, 'contact': self.contact, 'messages': self.best,
                 'updated_at': time.time() * 1000, 'phase': phase}
        if self.callback:
            self.callback(deepcopy(value))
        if self.device:
            path = progress_path(self.root, self.device)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix('.' + self.read_id + '.tmp')
                temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
                temp.replace(path)
            except OSError:
                pass  # Progress I/O must never interrupt phone capture.
