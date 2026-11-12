"""Temporary install, offline check and uninstall. Never starts the phone UI."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import winreg

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip().removeprefix('v')
BASE = ROOT / 'iphone_batch/.device-data/installer-validation'
TARGET = BASE / (VERSION + '-installed')
INSTALLER = ROOT / 'releases' / ('PhoneWorkbench-' + VERSION + '-Setup.exe')
REGKEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{AC8C7AE1-0C73-4989-B9F4-4A3F72B40760}_is1'


def main():
    for access in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGKEY, 0, access):
                raise RuntimeError('An existing installed client was found; temporary install would change its registration')
        except FileNotFoundError:
            pass
    if TARGET.exists():
        raise RuntimeError('Temporary install target already exists; refusing to overwrite')
    BASE.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(INSTALLER), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                    '/NOICONS', '/MERGETASKS=!desktopicon', '/DIR=' + str(TARGET),
                    '/LOG=' + str(BASE / 'install.log')], check=True, timeout=240)
    report = BASE / 'installed-check.json'
    try:
        subprocess.run([str(TARGET / 'PhoneWorkbench.exe'), '--check-install', str(report)], check=True, timeout=90)
        result = json.loads(report.read_text(encoding='utf-8'))
        assert result['ok'] and Path(result['root']).resolve() == TARGET.resolve(), result
        assert (TARGET / '使用说明.txt').is_file()
    finally:
        subprocess.run([str(TARGET / 'unins000.exe'), '/VERYSILENT', '/SUPPRESSMSGBOXES',
                        '/NORESTART', '/LOG=' + str(BASE / 'uninstall.log')], check=True, timeout=120)
    assert not (TARGET / 'PhoneWorkbench.exe').exists(), 'Uninstall did not remove the client'
    summary = {'ok': True, 'version': VERSION, 'installed_import_check': result,
        'install_exit': 0, 'uninstall_exit': 0,
        'installer_sha256': hashlib.file_digest(INSTALLER.open('rb'), 'sha256').hexdigest(),
        'phone_ui_started': False, 'phone_connections_tested': False}
    output = ROOT / 'releases' / ('PhoneWorkbench-' + VERSION + '-installation-check.json')
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ok': True, 'install': 'passed', 'offline_imports': 'passed', 'uninstall': 'passed', 'report': str(output)}))


if __name__ == '__main__':
    main()
