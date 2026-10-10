"""Archive the latest verified reply; this script never invokes a send action."""
import json
from workspace_service import WorkspaceService, ROOT

device = '00008030-001119CE0A93402E'
service = WorkspaceService()
records = [json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'workspace'/'replies').glob('*.json')]
verified = [r for r in records if r.get('device')==device and r.get('status')=='sent_verified']
if not verified:
    print(json.dumps({'backfill': 'no_verified_replies'}))
else:
    record = max(verified, key=lambda r:r.get('sent_at',r.get('created','')))
    destination = ROOT/'diagnostics'/('sms-sent-'+record['id']+'-translated.json')
    if destination.exists():
        print(json.dumps({'backfill':'already_archived','conversation_id':destination.stem}))
    else:
        current = service.native(device, 'capture', 'http://127.0.0.1:8080')
        if current.get('phone_number') != record['phone_number']:
            raise ValueError('当前手机会话不是最近人工回复的收件人，未修改阅读区')
        sent = next((m for m in reversed(current['messages'])
                     if m['side']=='outgoing' and m['text']==record['english']), None)
        if sent is None:
            raise ValueError('当前读取中未找到已确认的人工回复，未修改阅读区')
        result = service.save_sent_conversation(device, record,
            {'status':'sent_verified','conversation':current,'sent_message':sent})
        print(json.dumps({'backfill':'archived','conversation_id':result['conversation_id'],
                          'message_count':len(result['conversation']['messages'])}))
