"""Launch the isolated phone VNC servers and standalone TightVNC windows."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

DATA = Path(__file__).resolve().parent
ROOT = DATA.parents[1]
SOURCE = DATA / 'upstream-pymobiledevice3-v11.51.0'
PYTHON = ROOT / '.venv/Scripts/python.exe'
VIEWER = SOURCE / 'TightVNC/PFiles/TightVNC/tvnviewer.exe'
LOGS = DATA / 'logs'
DEVICES = {
    5901: '00008030-001275241E8B802E',
    5902: '00008030-001225443E33C02E',
    5903: '00008030-000315A00EB9402E',
    5904: '00008030-001515510132402E',
    5905: '00008030-001268E626C0C02E',
    5906: '00008030-000E60161E79402E',
    5907: '00008030-001944362185402E',
    5908: '00008030-001838463A78802E',
    5909: '00008030-001D25540A91802E',
    5910: '00008030-001619C136F2802E',
    5911: '00008030-001E301922D8402E',
    5912: '00008030-001C481A3C32802E',
}


def available(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5) as s:
            return s.recv(12).startswith(b'RFB ')
    except OSError:
        return False


def main():
    if not VIEWER.is_file():
        raise FileNotFoundError(VIEWER)
    LOGS.mkdir(exist_ok=True)
    servers = {}
    for port, udid in DEVICES.items():
        if '--existing-only' in sys.argv:
            continue
        if available(port):
            continue
        env = os.environ.copy()
        env.update(PYTHONPATH=str(SOURCE), PYMOBILEDEVICE3_UDID=udid, PYTHONUTF8='1')
        with (LOGS / f'isolated-vnc-{port}.out.log').open('w', encoding='utf-8') as out:
            with (LOGS / f'isolated-vnc-{port}.err.log').open('w', encoding='utf-8') as err:
                p = subprocess.Popen([str(PYTHON), '-m', 'pymobiledevice3',
                    'developer', 'core-device', 'display', 'serve-vnc', '--port',
                    str(port), '--decoder', 'av', '--userspace'], cwd=SOURCE,
                    env=env, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
                servers[port] = p.pid
    print('Started isolated servers:', servers, flush=True)
    deadline = time.monotonic() + (8 if '--existing-only' in sys.argv else 70)
    pending = set(DEVICES)
    viewers = {}
    while pending and time.monotonic() < deadline:
        for port in sorted(pending):
            if not available(port):
                continue
            p = subprocess.Popen([str(VIEWER), '-host=127.0.0.1', f'-port={port}',
                '-password=isolated', '-scale=20', '-fullscreen=no', '-showcontrols=no', '-viewonly=no', '-useclipboard=no'],
                cwd=VIEWER.parent)
            viewers[port] = p.pid
            pending.remove(port)
            print(f'Opened independent TightVNC: {port} {DEVICES[port]}', flush=True)
        time.sleep(1)
    arrange(viewers)
    result = {'servers': servers, 'viewers': viewers, 'unavailable': sorted(pending),
              'devices': DEVICES, 'time': time.strftime('%Y-%m-%d %H:%M:%S')}
    (DATA / 'isolated-vnc-windows.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


def arrange(viewers):
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SetWindowPos.restype = wintypes.BOOL
    try:
        user32.SetProcessDPIAware()
    except OSError:
        pass
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
    width, height = (rect.right - rect.left) // 10, (rect.bottom - rect.top) // 2
    wanted = {pid: port for port, pid in viewers.items()}
    found = set()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in wanted or not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        title = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title, 512)
        if 'iPhone screen' not in title.value and not title.value.startswith('VNC '):
            return True
        port = wanted[pid.value]
        index = port - 5901
        user32.ShowWindow(hwnd, 9)
        user32.SetWindowTextW(hwnd, f'VNC {port} | {DEVICES[port][-12:]}')
        moved = user32.SetWindowPos(hwnd, wintypes.HWND(-1), rect.left + index % 10 * width,
                            rect.top + index // 10 * height, width, height, 0x0050)
        if moved:
            found.add(port)
        return True

    for _ in range(12):
        user32.EnumWindows(visit, 0)
        if len(found) == len(viewers):
            break
        time.sleep(0.5)
    print('Arranged native VNC windows:', sorted(found), flush=True)


if __name__ == '__main__':
    if '--arrange-only' in sys.argv:
        state = json.loads((DATA / 'isolated-vnc-windows.json').read_text(encoding='utf-8'))
        arrange({int(port): pid for port, pid in state['viewers'].items()})
    else:
        main()
