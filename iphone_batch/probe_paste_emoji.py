import json
from demo_reply import DemoPhone
p=DemoPhone();p.select('00008030-001C481A3C32802E')
context=p.read_context()
print(json.dumps({'status':'paste_start','contact':context['contact']}),flush=True)
p.tap(.42,.938)
p.request('/host-clipboard',{'text':'🙂'})
p.request('/clipboard',{'text':'🙂'})
p.keys([0xE3,0x19])
items=p.native_items()
print(json.dumps({'status':'paste_checked','composer':[i.get('caption') for i in items if i.get('caption','').startswith('Message, ')],'has_send_control':any('Send' in i.get('caption','') for i in items)},ensure_ascii=True),flush=True)
p.frame().save('D:/qunkong/iphone_batch/.device-data/diagnostics/emoji-paste-current.png')
