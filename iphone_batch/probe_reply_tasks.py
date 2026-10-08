from reply_assistant import ReplyStore
import json
for t in ReplyStore().tasks()[:2]:
    print(json.dumps({'candidate':t.get('candidate'),'contact':t.get('contact'),'error':t.get('error')},ensure_ascii=True))
