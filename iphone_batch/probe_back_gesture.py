"""Verify native Messages back gesture without screenshots or image coordinates."""
import json
import subprocess
import time
import urllib.request
from controller import command_for, device_environment

DEVICE='00008030-001C481A3C32802E'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(base,path,body=None):
    req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='GET' if body is None else 'POST')
    with opener.open(req,timeout=10) as response:
        raw=response.read()
    try:return json.loads(raw)
    except ValueError:return raw.decode()
def items():
    result=subprocess.run(command_for(DEVICE,['developer','accessibility','list-items']),env=device_environment(DEVICE),capture_output=True,text=True,encoding='utf-8',timeout=25)
    if result.returncode:raise RuntimeError('Native UI read failed')
    return json.loads(result.stdout)

before=items()
if not any(', Show Conversation Details, Button' in (i.get('caption') or '') for i in before):
    print(json.dumps({'status':'not_in_conversation','gesture_executed':False}))
else:
    state=request('http://127.0.0.1:8070','/api/state')
    device=next(d for d in state['devices'] if d['udid']==DEVICE and d['ready'])
    request('http://127.0.0.1:8070','/api/select',{'udid':DEVICE})
    base='http://127.0.0.1:'+str(device['port'])
    end_x=round(.72*65535);y=32768
    try:
        for index in range(19):
            x=round((.008+(.72-.008)*index/18)*65535)
            request(base,'/touch',{'type':'contact','x':x,'y':y})
            time.sleep(.025)
    finally:
        request(base,'/touch',{'type':'release','x':end_x,'y':y})
    time.sleep(.7)
    after=items();captions=[i.get('caption') or '' for i in after]
    title=next((t for t in captions if t.endswith(', Header')),None)
    print(json.dumps({'status':'gesture_checked','title':title,'conversation_header_remaining':any(', Show Conversation Details, Button' in t for t in captions),'unread_rows':sum(', Unread, ' in t for t in captions),'send_clicked':False},ensure_ascii=True))
