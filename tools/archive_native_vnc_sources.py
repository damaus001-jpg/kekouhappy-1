"""Capture the isolated client and tracked upstream working tree, excluding runtime data."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit,urlunsplit

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'iphone_batch/.device-data'
UPSTREAM=DATA/'upstream-pymobiledevice3-v11.51.0'
TARGET=ROOT/'native_vnc_source'
CLIENTS=[
 'check_native_install.py',
 'native_vnc_workbench.pyw','native_vnc_worker.py','start_native_vnc_dev.pyw','vnc_av_continuous.py',
 'native_bubble_records.py','native_decode_accel.py','native_device_control.py','native_history_reader.py',
 'native_keyboard_policy.py','native_process_owner.py','native_reverse_reader.py','isolated_vnc_windows.py',
 'check_pending_developer_state.py','check_trust_status.py','prepare_pending_ddi.py','reestablish_pending_trust.py',
 'reparse_native_bubbles.py','reveal_pending_developer.py','verify_pair_sources.py',
 'test_native_bubble_records.py','test_native_decode_accel.py','test_native_history_reader.py',
 'test_native_keyboard_policy.py','test_native_process_owner.py','test_native_reverse_reader.py',
]


def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+UPSTREAM.as_posix(),'-C',str(UPSTREAM),*args])


def copy(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    if source.is_symlink():
        destination.write_text(source.readlink().as_posix(),encoding='utf-8')
    else:
        content=source.read_bytes()
        if b'\0' not in content:content=content.replace(b'\r\n',b'\n')
        destination.write_bytes(content)


def main():
    for name in CLIENTS:copy(DATA/name,TARGET/'client'/name)
    files=[p for p in git('ls-files','-z').decode('utf-8').split('\0') if p]
    for name in files:
        target=TARGET/'upstream'/name
        if not target.resolve().is_relative_to((TARGET/'upstream').resolve()):raise ValueError('Unsafe source path')
        copy(UPSTREAM/name,target)
    viewer=UPSTREAM/'TightVNC/PFiles/TightVNC'
    for name in ('tvnviewer.exe','LICENSE.txt'):
        copy(viewer/name,TARGET/'viewer/TightVNC/PFiles/TightVNC'/name)
    copy(DATA/'desktop_workbench.pyw',TARGET/'legacy_experiment/desktop_workbench.pyw')
    (TARGET/'upstream-working-tree.patch').write_bytes(git('diff','--binary','HEAD'))
    remote=git('remote','get-url','origin').decode().strip()
    url=urlsplit(remote)
    if url.hostname:remote=urlunsplit((url.scheme,url.hostname,url.path,'',''))
    metadata={'archive_version':'v'+(ROOT/'VERSION').read_text(encoding='utf-8').strip().removeprefix('v'),'upstream_commit':git('rev-parse','HEAD').decode().strip(),
        'upstream_remote':remote,'upstream_working_tree_modified':True,
        'upstream_files':len(files),'client_files':CLIENTS,'text_line_endings':'LF (archive normalized)',
        'installed_packages':{n:importlib.metadata.version(n) for n in
            ('pymobiledevice3','av','psutil','pywin32','pyinstaller','pyinstaller-hooks-contrib')}}
    (TARGET/'SOURCE_METADATA.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    manifest={}
    for path in sorted(TARGET.rglob('*')):
        if path.is_file() and path.name!='SHA256SUMS.json':
            manifest[path.relative_to(TARGET).as_posix()]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    (TARGET/'SHA256SUMS.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
    print(json.dumps({'snapshot_files':len(manifest),'total_bytes':sum(v['bytes'] for v in manifest.values()),
        'client_files':len(CLIENTS),'upstream_files':len(files),'target':str(TARGET)},ensure_ascii=True))


if __name__=='__main__':main()
