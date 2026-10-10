"""Count transports in the existing backup without reading message bodies."""
import hashlib
import json
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent / '.device-data'
backup = root / 'sms-backup' / '00008030-001119CE0A93402E'
file_id = hashlib.sha1(b'HomeDomain-Library/SMS/sms.db').hexdigest()
with sqlite3.connect((backup / file_id[:2] / file_id).as_uri() + '?mode=ro', uri=True) as db:
    counts = dict(db.execute('SELECT service, COUNT(*) FROM message GROUP BY service'))
print(json.dumps({'snapshot_message_services': counts}))
