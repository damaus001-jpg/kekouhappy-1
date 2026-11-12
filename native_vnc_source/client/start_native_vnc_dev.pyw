"""Desktop entry point: gracefully restart the source-based native client."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

DATA = Path(__file__).resolve().parent
ROOT = DATA.parents[1]
APP = DATA / 'native_vnc_workbench.pyw'


def notify(text):
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo('手机群控开发版', text, parent=root)
    root.destroy()


def main():
    kernel = ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    mutex = kernel.CreateMutexW(None, False, 'Local\\NativeVNCWorkbenchDevLauncher')
    if kernel.GetLastError() == 183:
        if mutex:
            kernel.CloseHandle(mutex)
        return
    try:
        existing = []
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                name = (proc.info['name'] or '').lower()
                args = proc.info['cmdline'] or []
                if name.startswith('python') and any(Path(a).name == 'native_vnc_worker.py' for a in args):
                    notify('当前有短信读取或输入操作正在进行。请等操作结束后，再双击开发版快捷方式。')
                    return
                if name == 'nativevncworkbench.exe' or (name.startswith('python') and
                        any(Path(a).name == APP.name for a in args)):
                    existing.append(proc)
            except (psutil.Error, ValueError, OSError):
                continue
        if existing:
            pids = {p.pid for p in existing}
            user = ctypes.windll.user32
            user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def visit(hwnd, _):
                pid = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value in pids:
                    title = ctypes.create_unicode_buffer(256)
                    user.GetWindowTextW(hwnd, title, 256)
                    if title.value.startswith('手机群控'):
                        user.PostMessageW(hwnd, 0x0010, 0, 0)
                return True
            user.EnumWindows(visit, 0)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and any(p.is_running() for p in existing):
                time.sleep(.2)
            if any(p.is_running() for p in existing):
                notify('现有客户端尚未退出。请先关闭原窗口，再双击开发版；没有重复启动。')
                return
        env = os.environ.copy()
        env.update(PYTHONUTF8='1', NATIVE_VNC_DEV='1', NATIVE_VNC_MAX_DEVICES='20')
        log = DATA / 'logs/native-vnc-dev-startup.log'
        log.parent.mkdir(exist_ok=True)
        with log.open('a', encoding='utf-8') as output:
            subprocess.Popen([str(ROOT / '.venv/Scripts/pythonw.exe'), str(APP)],
                cwd=ROOT, env=env, stdout=output, stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        if mutex:
            kernel.CloseHandle(mutex)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        notify('开发版启动失败：' + str(exc))
