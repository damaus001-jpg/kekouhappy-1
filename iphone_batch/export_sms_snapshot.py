"""Export every snapshot record by message ID; unread state is snapshot-time state."""
import base64
import csv
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typedstream import unarchive_from_data
from typedstream.types.foundation import NSString

root=Path(__file__).resolve().parent/'.device-data'
device='00008030-001119CE0A93402E'
backup=root/'sms-backup'/device
file_id=hashlib.sha1(b'HomeDomain-Library/SMS/sms.db').hexdigest()
connection=sqlite3.connect((backup/file_id[:2]/file_id).as_uri()+'?mode=ro',uri=True)
connection.row_factory=sqlite3.Row


def body_text(blob):
    archived=unarchive_from_data(blob)
    while archived is not None:
        clazz=getattr(archived,'clazz',None)
        if clazz is not None and clazz.name not in (b'NSAttributedString',b'NSMutableAttributedString'):
            raise ValueError('Unexpected attributed body class')
        for item in getattr(archived,'contents',[]):
            value=getattr(item,'value',item)
            if isinstance(value,NSString):
                return value.value
        archived=getattr(archived,'super_object',None)
    raise ValueError('Attributed body has no verified string')


try:
    started=time.perf_counter()
    records=[];decoded=0;unresolved=0
    for row in connection.execute('''select ROWID,guid,text,attributedBody,is_from_me,is_read,date,date_read,
        cache_has_attachments,associated_message_type,item_type from message order by date,ROWID'''):
        record=dict(row);record['message_id']=record.pop('ROWID')
        blob=record.pop('attributedBody')
        if record['text'] is None and blob:
            try:record['text']=body_text(blob);decoded+=1
            except Exception as error:
                unresolved+=1;record['decode_error']=str(error)
                record['attributed_body_base64']=base64.b64encode(blob).decode('ascii')
        records.append(record)
    unread=[dict(row) for row in connection.execute('''select c.chat_identifier,count(distinct m.ROWID) as unread_messages
        from message m join chat_message_join j on j.message_id=m.ROWID join chat c on c.ROWID=j.chat_id
        where m.is_from_me=0 and m.is_read=0 and m.item_type=0 and m.associated_message_type=0
        group by c.ROWID order by c.chat_identifier''')]
    expected=connection.execute('select count(*) from message').fetchone()[0]
    summary={'records':len(records),'expected_records':expected,'all_row_ids_unique':len({r['message_id'] for r in records})==expected,
             'rich_text_decoded':decoded,'unresolved_bodies':unresolved,'read_decode_seconds':round(time.perf_counter()-started,6),
             'unread_conversations_at_snapshot':len(unread),'unread_messages_at_snapshot':sum(r['unread_messages'] for r in unread)}
    destination=root/'sms-export';destination.mkdir(exist_ok=True)
    (destination/'messages.json').write_text(json.dumps({'device':device,'source':'local-backup-snapshot','summary':summary,
        'messages':records,'unread_at_snapshot':unread},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))
finally:connection.close()
