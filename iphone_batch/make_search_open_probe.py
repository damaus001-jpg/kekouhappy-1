from pathlib import Path
s=Path('probe_native_keyboard_search.py').read_text(encoding='utf-8-sig')
s=s.replace("for keys in ([],[0xE3],[0xE3,0x09],[0xE3],[]):", "for keys in ([],[0x51],[],[0x28],[]):")
s=s.replace("s=req('http", "if '9032619764, Search Field' not in before or '+1 (903) 261-9764, Button' not in before:raise RuntimeError('Exact search result not confirmed')\ns=req('http")
s=s.replace("'after_cmd_f'", "'after_down_return'")
Path('probe_native_search_open.py').write_text(s,encoding='utf-8')
