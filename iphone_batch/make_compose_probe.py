from pathlib import Path
s=Path('probe_native_keyboard_search.py').read_text(encoding='utf-8-sig')
s=s.replace('[0xE3,0x09]','[0xE3,0x11]').replace("'after_cmd_f'", "'after_cmd_n'")
Path('probe_native_keyboard_compose.py').write_text(s,encoding='utf-8')
