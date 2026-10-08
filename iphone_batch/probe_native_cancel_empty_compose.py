"""Test native Messages keyboard search; no screenshot or send."""
import json,subprocess,time,urllib.request
from pathlib import Path
from controller import command_for,device_environment
DEVICE='00008030-001C481A3C32802E'
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def req(base,path,body=None):
    r=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with opener.open(r,timeout=10) as response:raw=response.read()
    try:return json.loads(raw)
    except ValueError:return raw.decode()
def captions():
    import sys
    p=subprocess.run([sys.executable,str(Path(__file__).with_name('native_ui_scan.py'))],capture_output=True,encoding='utf-8',timeout=30)
    if p.returncode:raise RuntimeError(p.stderr[-500:])
    return json.loads(p.stdout)['captions']

before=captions();print(json.dumps({'before':before}),flush=True)
if not any(c.startswith('New iMessage, Show Conversation Details, Button') for c in before):raise RuntimeError('Expected empty new conversation not confirmed')
if 'Message, iMessage' not in before:raise RuntimeError('Empty composer not confirmed')
s=req('http://127.0.0.1:8070','/api/state');d=next(d for d in s['devices'] if d['udid']==DEVICE and d['ready'])
req('http://127.0.0.1:8070','/api/select',{'udid':DEVICE});base='http://127.0.0.1:'+str(d['port'])
try:
    for keys in ([],[0x29],[]):
        req(base,'/key',{'usages':keys});time.sleep(.15)
finally:req(base,'/key',{'usages':[]})
time.sleep(.6)
print(json.dumps({'after_escape_empty_compose':captions(),'send_clicked':False}),flush=True)
