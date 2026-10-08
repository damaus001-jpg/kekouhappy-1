import json
import time
from demo_reply import DemoPhone
p=DemoPhone();p.select('00008030-001C481A3C32802E')
items=p.native_items()
composers=[i.get('caption','') for i in items if i.get('caption','').startswith('Message, ')]
if 'Message, v' in composers:
    p.keys([0x2A])
p.request('/host-clipboard',{'text':'good night'})
p.request('/clipboard',{'text':'good night'})
try:
    for usages in ([0xE3],[0xE3,0x19],[0xE3]):
        p.request('/key',{'usages':usages});time.sleep(.2)
finally:
    p.request('/key',{'usages':[]})
time.sleep(.7)
items=p.native_items()
print(json.dumps({'status':'paste_check','composer':[i.get('caption','') for i in items if i.get('caption','').startswith('Message, ')],'send_clicked':False},ensure_ascii=True),flush=True)
p.frame().save('D:/qunkong/iphone_batch/.device-data/diagnostics/good-night-paste.png')
