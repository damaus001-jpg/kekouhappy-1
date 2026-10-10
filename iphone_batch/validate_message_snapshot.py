"""Check existing backup integration without exposing message bodies."""
import json
from pathlib import Path
from message_backup import read_snapshot

root = Path(__file__).resolve().parent / '.device-data'
device = '00008030-001119CE0A93402E'
summary = []
for contact in ('+14303142530', '+13153602544'):
    snapshot = read_snapshot(root, device, contact)
    messages = snapshot['messages']
    summary.append({'contact': contact, 'records': len(messages),
                    'unique_message_ids': len({m['message_id'] for m in messages}),
                    'decode_errors': sum('decode_error' in m for m in messages),
                    'transports': sorted({m['transport'] for m in messages})})
print(json.dumps(summary))
