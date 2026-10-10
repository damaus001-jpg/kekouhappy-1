"""Read-only integrity and timing audit of the completed local SMS snapshot."""
import hashlib
import json
import plistlib
import sqlite3
import time
from pathlib import Path

device='00008030-001119CE0A93402E'
root=Path(__file__).resolve().parent/'.device-data'/'sms-backup'/device
status=plistlib.loads((root/'Status.plist').read_bytes())
manifest=plistlib.loads((root/'Manifest.plist').read_bytes())
result={'snapshot_state':status.get('SnapshotState'), 'encrypted':manifest.get('IsEncrypted')}
if result['snapshot_state']!='finished':
    raise ValueError('Backup is not completed; no completeness claim is allowed')
if result['encrypted']:
    print(json.dumps(result));raise SystemExit('Encrypted snapshot requires its existing backup password')
file_id=hashlib.sha1(b'HomeDomain-Library/SMS/sms.db').hexdigest()
path=root/file_id[:2]/file_id
connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
connection.row_factory=sqlite3.Row
try:
    result['integrity']=connection.execute('pragma integrity_check').fetchone()[0]
    result['message_count']=connection.execute('select count(*) from message').fetchone()[0]
    result['chat_count']=connection.execute('select count(*) from chat').fetchone()[0]
    started=time.perf_counter()
    records=connection.execute('select ROWID,guid,text,is_from_me,date,handle_id from message order by date,ROWID').fetchall()
    result['read_all_seconds']=round(time.perf_counter()-started,6)
    result['read_count']=len(records)
    result['row_ids_unique']=len({r['ROWID'] for r in records})==len(records)
    result['null_text_count']=sum(r['text'] is None for r in records)
    result['attributed_body_without_text']=connection.execute('select count(*) from message where text is null and length(attributedBody)>0').fetchone()[0]
    result['attachment_rows']=connection.execute('select count(*) from message where cache_has_attachments=1').fetchone()[0]
    result['guid_duplicates']=connection.execute('select count(*)-count(distinct guid) from message').fetchone()[0]
    result['selected_conversation_counts']=[dict(r) for r in connection.execute('''select c.chat_identifier,count(*) as messages
        from chat c join chat_message_join j on j.chat_id=c.ROWID
        where c.chat_identifier in (?,?) group by c.ROWID''',('+14303142530','+13153602544'))]
    (root.parent/'sms-database-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
finally:connection.close()
