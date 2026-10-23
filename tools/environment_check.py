"""Read-only environment check: never touches a phone or sends a message."""
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def check(root):
    lock = root / 'requirements-windows.lock.txt'
    mismatches = []
    for line in lock.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.split('==')
        try:
            if importlib.metadata.version(name) != version:
                mismatches.append(name)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(name)
    node = shutil.which('node')
    if not node and os.name == 'nt':
        candidate = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'nodejs/node.exe'
        if candidate.exists():
            node = str(candidate)
    node_ok = bool(node and subprocess.run([node, '-e', 'process.exit(Number(process.versions.node.split(".")[0])>=24?0:1)'], capture_output=True).returncode == 0)
    browser = any((Path(os.environ.get(base, '')) / path).is_file() for base, path in [
        ('ProgramFiles', 'Google/Chrome/Application/chrome.exe'),
        ('ProgramFiles(x86)', 'Microsoft/Edge/Application/msedge.exe'),
        ('ProgramFiles', 'Microsoft/Edge/Application/msedge.exe'),
        ('LOCALAPPDATA', 'Google/Chrome/Application/chrome.exe')])
    driver = False
    if os.name == 'nt':
        driver = subprocess.run(['sc.exe', 'query', 'Apple Mobile Device Service'], capture_output=True).returncode == 0
    imports = all(importlib.util.find_spec(name) is not None for name in ['pymobiledevice3', 'rapidocr', 'onnxruntime', 'cryptography', 'PIL', 'psutil'])
    config = root / 'iphone_batch/.device-data/deepseek.json'
    from_env = bool(os.environ.get('DEEPSEEK_API_KEY'))
    return {'python_3_13_x64': sys.version_info[:2] == (3,13) and platform.machine().endswith('64'),
            'dependency_mismatches': mismatches, 'imports': imports, 'node_24_plus': node_ok,
            'browser': browser, 'apple_driver_installed': driver,
            'translation_configuration_present': config.is_file() or from_env,
            'note': 'Phone trust/developer mode and ChatGPT login require manual verification.'}


if __name__ == '__main__':
    result = check(Path(__file__).resolve().parents[1])
    print(json.dumps(result, ensure_ascii=True, indent=2))
    # No phone or API configuration is required to restore data or preview the UI.
    sys.exit(0 if result['python_3_13_x64'] and not result['dependency_mismatches'] and result['imports'] and result['node_24_plus'] and result['browser'] else 1)
