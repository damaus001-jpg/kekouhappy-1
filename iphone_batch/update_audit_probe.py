from pathlib import Path
p=Path('probe_native_audit_rects.py')
s=p.read_text(encoding='utf-8-sig').replace('s.run_audit([100])',"s.run_audit(['testTypeHitRegion'])")
p.write_text(s,encoding='utf-8')
