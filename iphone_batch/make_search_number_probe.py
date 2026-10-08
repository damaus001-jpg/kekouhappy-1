from pathlib import Path
p=Path('probe_native_keyboard_search.py')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("for keys in ([],[0xE3],[0xE3,0x09],[0xE3],[]):", "for keys in ([],):")
s=s.replace("time.sleep(.6)\nprint", "for ch in '9032619764':\n    code=0x27 if ch=='0' else 0x1E+int(ch)-1\n    req(base,'/key',{'usages':[code]});time.sleep(.06)\n    req(base,'/key',{'usages':[]});time.sleep(.06)\ntime.sleep(.8)\nprint")
s=s.replace("'after_cmd_f'", "'after_search_number'")
s=s.replace("s=req('http", "if not any(c=='close, Button' for c in before):raise RuntimeError('Search state not confirmed')\ns=req('http")
Path('probe_native_search_number.py').write_text(s,encoding='utf-8')
