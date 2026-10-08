from pathlib import Path
p=Path('probe_native_cancel_empty_compose.py')
s=p.read_text(encoding='utf-8')
a=s.index('def captions():');b=s.index('\nbefore=captions()',a)
s=s[:a]+'''def captions():
    import sys
    p=subprocess.run([sys.executable,str(Path(__file__).with_name('native_ui_scan.py'))],capture_output=True,encoding='utf-8',timeout=30)
    if p.returncode:raise RuntimeError(p.stderr[-500:])
    return json.loads(p.stdout)['captions']
'''+s[b:]
s=s.replace('import json,subprocess,time,urllib.request','import json,subprocess,time,urllib.request\nfrom pathlib import Path')
p.write_text(s,encoding='utf-8')
