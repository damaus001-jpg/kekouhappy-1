"""Preserve occurrences; only append after a unique contiguous overlap."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid


def key(message):
    return (message.get('side'), message.get('text'), message.get('kind', 'text'))


def append_window(history, window):
    if not history:
        return deepcopy(window), True
    old, new = list(map(key, history)), list(map(key, window))
    for size in range(min(len(old), len(new), 8), 0, -1):
        if size < 2 and len(old) > 1:
            break
        anchor = old[-size:]
        positions = [i for i in range(len(new)-size+1) if new[i:i+size] == anchor]
        if not positions:
            continue
        previous = [i for i in range(len(old)-size+1) if old[i:i+size] == anchor]
        if len(positions) != 1 or len(previous) != 1:
            return deepcopy(history), False
        return deepcopy(history) + deepcopy(window[positions[0]+size:]), True
    return deepcopy(history), False


class MessageLedger:
    def __init__(self, root):
        self.directory = Path(root) / 'workspace' / 'message-ledger'

    def path(self, device, contact):
        name = hashlib.sha256(json.dumps([device, contact]).encode()).hexdigest()
        return self.directory / (name + '.json')

    def load(self, device, contact):
        path = self.path(device, contact)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding='utf-8'))
        if value['device'] != device or value['contact'] != contact:
            raise ValueError('消息记录的设备或会话不一致')
        return value

    def commit(self, device, contact, history, window, aligned, snapshot=None, pending=None):
        messages = deepcopy(history)
        for index, message in enumerate(messages, 1):
            message.setdefault('message_id', 'ui:' + uuid.uuid4().hex)
            message.setdefault('record_source', 'native-ui')
            message['sequence'] = index
        value = {'device': device, 'contact': contact, 'messages': messages,
                 'last_window': deepcopy(window), 'overlap_confirmed': aligned,
                 'snapshot': snapshot, 'pending_windows': pending or [],
                 'updated': datetime.now(timezone.utc).isoformat(), 'history_complete': False}
        path = self.path(device, contact)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        return value
