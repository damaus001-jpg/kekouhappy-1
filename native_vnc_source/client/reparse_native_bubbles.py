"""Repair parser-v1 archives from their saved accessibility text, preserving originals."""
from datetime import datetime
import json
from pathlib import Path
import sys
import uuid

DATA=Path(__file__).resolve().parent
sys.path.insert(0,str(DATA.parent))
from native_bubble_records import parse_bubble_records

for path in sorted((DATA/'diagnostics').glob('native-desktop-*-reading.json')):
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('source')!='native-reverse-until-number' or value.get('parser_version',1)>=2:
        continue
    records=value.get('raw_elements',[])
    contact=value.get('contact')
    if not records or not contact:
        continue
    messages,unknown=parse_bubble_records(records,contact)
    if not messages:
        continue
    old=value.get('messages',[])
    changes=sum(a.get('text')!=b.get('text') or a.get('time')!=b.get('time') for a,b in zip(old,messages))
    value.update(messages=messages,unclassified=unknown,parser_version=2,
        reparsed_from=path.stem,reparsed_at=datetime.now().isoformat(),
        scope='已按原始界面结构逐条重新解析，修复节点 ID 复用并关联日期；不是本次手机新读取，数据库历史完整性未核对')
    target=path.parent/('native-desktop-reparsed-'+uuid.uuid4().hex+'-reading.json')
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'original':path.name,'repaired':target.name,'messages':len(messages),
        'corrected_occurrences':changes,'dated_messages':sum(bool(m.get('date_label')) for m in messages)},ensure_ascii=True),flush=True)
