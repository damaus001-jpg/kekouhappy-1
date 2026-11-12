"""Verify and restore this source snapshot without deleting local phone data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    source=Path(__file__).resolve().parent
    root=source.parent
    data=root/'iphone_batch/.device-data'
    manifest=json.loads((source/'SHA256SUMS.json').read_text(encoding='utf-8'))
    for name,record in manifest.items():
        path=(source/name).resolve()
        if not path.is_relative_to(source.resolve()):raise SystemExit('Invalid manifest path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            raise SystemExit('Snapshot hash mismatch: '+name)
    destinations=[]
    for folder,target in [('client',data),('upstream',data/'upstream-pymobiledevice3-v11.51.0'),
                          ('viewer',data/'upstream-pymobiledevice3-v11.51.0')]:
        for path in sorted((source/folder).rglob('*')):
            if path.is_file():destinations.append((path,target/path.relative_to(source/folder)))
    conflicts=[str(dst.relative_to(root)) for src,dst in destinations
               if dst.exists() and src.read_bytes()!=dst.read_bytes()]
    if conflicts and not args.overwrite:
        raise SystemExit('Different runtime files exist; use --overwrite to restore deliberately:\n'+'\n'.join(conflicts))
    for src,dst in destinations:
        if not dst.resolve().is_relative_to(data.resolve()):raise SystemExit('Invalid destination')
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dst)
    print(f'Restored {len(destinations)} files. No services started; local phone data retained.')


if __name__=='__main__':main()
