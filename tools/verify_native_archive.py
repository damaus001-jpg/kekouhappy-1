"""Check source manifest against the working tree and staged Git blobs."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'native_vnc_source'


def main():
    records = json.loads((SNAPSHOT / 'SHA256SUMS.json').read_text(encoding='utf-8'))
    names = ['native_vnc_source/' + name for name in records]
    for name, record in records.items():
        content = (SNAPSHOT / name).read_bytes()
        assert len(content) == record['bytes'], name
        assert hashlib.sha256(content).hexdigest() == record['sha256'], name
    data = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(),
        'cat-file', '--batch'], cwd=ROOT, input=''.join(':' + name + '\n' for name in names).encode())
    offset = 0
    for name, record in zip(names, records.values()):
        end = data.index(b'\n', offset)
        header = data[offset:end].split()
        assert len(header) == 3 and header[1] == b'blob', name
        size = int(header[2])
        content = data[end+1:end+1+size]
        assert hashlib.sha256(content).hexdigest() == record['sha256'], 'Staged content differs: ' + name
        offset = end + 1 + size + 1
    print(f'PASS: {len(records)} snapshot files match manifest and staged Git blobs')


if __name__ == '__main__':
    main()
