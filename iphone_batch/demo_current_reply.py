import json
import time
import uuid
from demo_reply import DemoPhone, DemoModel
from reply_assistant import ReplyAssistant, fingerprint

p=DemoPhone();device='00008030-001C481A3C32802E';p.select(device)
a=ReplyAssistant(p,model=DemoModel());a.device=device
context=p.read_context()
task={'id':uuid.uuid4().hex,'device':device,'status':'ready','created':time.time(),**context,
    'fingerprint':fingerprint(context['messages']),**DemoModel().suggest(context['contact'],context['messages'],{})}
a.store.save(task)
print(json.dumps({'status':'input_demo_start','task_id':task['id'],'reply':'🙂'}),flush=True)
result=a.send(task['id'],0)
print(json.dumps({'status':result['status'],'reply':result['sent_text'],'note':a.message}),flush=True)
