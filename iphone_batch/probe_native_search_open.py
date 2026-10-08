"""Test native Messages keyboard search; no screenshot or send."""
import json,subprocess,time,urllib.request
from controller import command_for,device_environment
DEVICE='00008030-001C481A3C32802E'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def req(base,path,body=None):
    r=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with opener.open(r,timeout=10) as response:raw=response.read()
    try:return json.loads(raw)
    except ValueError:return raw.decode()
def captions():
    p=subprocess.run(command_for(DEVICE,['developer','accessibility','list-items']),env=device_environment(DEVICE),capture_output=True,encoding='utf-8',timeout=25)
    if p.returncode:raise RuntimeError(p.stderr[-500:])
    return [i.get('caption','') for i in json.loads(p.stdout)]
before=captions();print(json.dumps({'before':before}),flush=True)
if any(', Show Conversation Details, Button' in c for c in before):raise RuntimeError('Refusing keyboard navigation in a conversation with possible draft')
if '9032619764, Search Field' not in before or '+1 (903) 261-9764, Button' not in before:raise RuntimeError('Exact search result not confirmed')
s=req('http://127.0.0.1:8070','/api/state');d=next(d for d in s['devices'] if d['udid']==DEVICE and d['ready'])
req('http://127.0.0.1:8070','/api/select',{'udid':DEVICE});base='http://127.0.0.1:'+str(d['port'])
try:
    for keys in ([],[0x51],[],[0x28],[]):
        req(base,'/key',{'usages':keys});time.sleep(.15)
finally:req(base,'/key',{'usages':[]})
time.sleep(.6)
print(json.dumps({'after_down_return':captions(),'send_clicked':False}),flush=True)
