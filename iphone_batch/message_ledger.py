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


def append_verified_window(history, window, *, skip_known_attachments=True):
    """Match the entire visible overlap against a unique history suffix.

    Database photo bodies and AX photo descriptions differ. They represent one
    attachment occurrence, not a text match. Ambiguous occurrences require a
    fresh database snapshot instead of guessing where to append.
    """
    def comparable(message):
        side, text, kind = key(message)
        return side, '' if kind == 'attachment' else text, kind
    old, new = list(map(comparable, history)), list(map(comparable, window))
    def unmatched():
        # Some AX windows omit photo elements entirely. Already backed-up
        # attachment occurrences remain in history; never skip a missing text.
        if (skip_known_attachments and history and history[-1].get('kind') != 'attachment'
                and any(m.get('kind') == 'attachment' for m in history)
                and not any(m.get('kind') == 'attachment' for m in window)):
            visible = [m for m in history if m.get('kind') != 'attachment']
            merged, aligned = append_verified_window(visible, window, skip_known_attachments=False)
            if aligned:
                return deepcopy(history) + merged[len(visible):], True
        return deepcopy(history), False
    if not old or not new:
        return unmatched()
    minimum = 1 if len(old) == 1 else 2
    for size in range(min(len(old), len(new), 8), minimum-1, -1):
        anchor = old[-size:]
        positions = [i for i in range(len(new)-size+1) if new[i:i+size] == anchor]
        if not positions:
            continue
        if len(positions) != 1 or sum(old[i:i+size] == anchor for i in range(len(old)-size+1)) != 1:
            return unmatched()
        end = positions[0]+size
        if end > len(old) or old[-end:] != new[:end]:
            return unmatched()
        for before, after in zip(history[-end:], window[:end]):
            # AX times can verify subsequent AX occurrences. Database times are
            # UTC and must not be compared with an assumed phone timezone.
            timestamp = before.get('time')
            if timestamp and 'T' not in timestamp and timestamp != after.get('time'):
                return unmatched()
        return deepcopy(history) + deepcopy(window[end:]), True
    return unmatched()


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

    def commit(self, device, contact, history, window, aligned, snapshot=None, pending=None,
               *, baseline_complete=False, conversation_id=None):
        messages = deepcopy(history)
        for index, message in enumerate(messages, 1):
            message.setdefault('message_id', 'ui:' + uuid.uuid4().hex)
            message.setdefault('record_source', 'native-ui')
            message['sequence'] = index
        value = {'device': device, 'contact': contact, 'messages': messages,
                 'last_window': deepcopy(window), 'overlap_confirmed': aligned,
                 'snapshot': snapshot, 'pending_windows': pending or [],
                 'updated': datetime.now(timezone.utc).isoformat(), 'history_complete': False,
                 'baseline_complete': baseline_complete, 'conversation_id': conversation_id}
        path = self.path(device, contact)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        return value
