"""Local desktop controls for this checkout's backend processes."""
import os
import ctypes
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.request
import urllib.error

import psutil

PROJECT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT / 'iphone_batch'
PYTHON = PROJECT / '.venv' / 'Scripts' / 'python.exe'
if not PYTHON.is_file():
    PYTHON = PROJECT / 'runtime' / 'python.exe'
LOGS = SCRIPTS / '.device-data' / 'logs'
ENTRIES = {'dashboard.py', 'controller.py', 'pmd_entry.py',
           'native_workspace.py', 'message_backup.py', 'device_trust.py', 'tunneld_entry.py'}
TUNNEL_ENTRY = SCRIPTS / 'tunneld_entry.py'
TUNNEL_STATE = LOGS / 'tunneld-owner.json'
TUNNEL_URL = 'http://127.0.0.1:49151'


def normalized(path):
    return os.path.normcase(os.path.abspath(path))


def process_entry(process):
    """Require both this environment and an exact script path, never a substring."""
    try:
        if normalized(process.exe()) != normalized(PYTHON):
            return None
        command = process.cmdline()
        if len(command) < 2 or command[1].startswith('-'):
            return None
        script = Path(command[1])
        if not script.is_absolute():
            script = Path(process.cwd()) / script
        return next((name for name in ENTRIES
                     if normalized(script) == normalized(SCRIPTS / name)), None)
    except psutil.NoSuchProcess:
        return None


class Backend:
    def __init__(self):
        self.started = None

    def processes(self):
        result = []
        for process in psutil.process_iter(['name']):
            if not (process.info['name'] or '').lower().startswith('python'):
                continue
            try:
                entry = process_entry(process)
            except psutil.AccessDenied as error:
                raise RuntimeError('无法检查部分 Python 进程，请使用运行后台的 Windows 账户。') from error
            if entry:
                result.append((process, entry))
        return result

    def status(self):
        processes = self.processes()
        dashboards = [p for p, entry in processes if entry == 'dashboard.py']
        if dashboards:
            tunnel = ' · 共享隧道在线' if self._tunneld_is_owned() and self._tunneld_healthy() else ' · 共享隧道未就绪'
            return f'后台运行中 · 主进程 {", ".join(str(p.pid) for p in dashboards)}{tunnel}'
        if processes:
            return f'主服务已停止，仍有 {len(processes)} 个相关进程，可点击彻底关闭'
        return '后台已关闭'

    def start(self):
        processes = self.processes()
        if any(entry == 'dashboard.py' for _, entry in processes):
            return '后台已经运行，无需重复启动。'
        unrelated = [(process, entry) for process, entry in processes if entry != 'tunneld_entry.py']
        if unrelated:
            raise RuntimeError('检测到残留进程，请先点击“彻底关闭后台”，再启动。')
        if not PYTHON.is_file():
            raise RuntimeError('缺少项目 Python 环境，请先运行 Install.ps1。')
        LOGS.mkdir(parents=True, exist_ok=True)
        self._ensure_tunneld()
        environment = os.environ.copy()
        node = Path(environment.get('ProgramFiles', r'C:\Program Files')) / 'nodejs'
        environment['PATH'] = str(node) + os.pathsep + environment.get('PATH', '')
        environment.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        with (LOGS / 'dashboard-8070.out.log').open('ab') as out, \
                (LOGS / 'dashboard-8070.err.log').open('ab') as err:
            process = subprocess.Popen(
                [str(PYTHON), str(SCRIPTS / 'dashboard.py'), '--port', '8070', '--base-port', '8080'],
                cwd=PROJECT, env=environment, stdout=out, stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.started = process
        time.sleep(2)
        if process.poll() is not None:
            self._stop_tunneld()
            raise RuntimeError('后台启动失败，请查看日志 dashboard-8070.err.log。')
        return '已启动后台和共享隧道，手机连接和投屏准备可能需要一些时间。请从授权客户端“苹果”入口访问。'

    @staticmethod
    def _tunneld_healthy():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(TUNNEL_URL + '/hello', timeout=0.8) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    @staticmethod
    def _tunneld_is_owned():
        try:
            state = json.loads(TUNNEL_STATE.read_text(encoding='utf-8'))
            process = psutil.Process(int(state['pid']))
            return (abs(process.create_time() - float(state['created'])) < 1.0
                    and process_entry(process) == 'tunneld_entry.py')
        except (OSError, ValueError, KeyError, TypeError, psutil.Error):
            return False

    @staticmethod
    def _store_tunneld_owner(pid):
        process = psutil.Process(pid)
        state = {'pid': pid, 'created': process.create_time(), 'entry': str(TUNNEL_ENTRY)}
        temporary = TUNNEL_STATE.with_suffix('.tmp')
        temporary.write_text(json.dumps(state), encoding='utf-8')
        os.replace(temporary, TUNNEL_STATE)

    @staticmethod
    def _launch_elevated_tunneld():
        if os.name != 'nt':
            raise RuntimeError('共享隧道的系统网络接口需要 Windows 管理员权限。')

        class ShellExecuteInfo(ctypes.Structure):
            _fields_ = [
                ('cbSize', ctypes.c_ulong), ('fMask', ctypes.c_ulong),
                ('hwnd', ctypes.c_void_p), ('lpVerb', ctypes.c_wchar_p),
                ('lpFile', ctypes.c_wchar_p), ('lpParameters', ctypes.c_wchar_p),
                ('lpDirectory', ctypes.c_wchar_p), ('nShow', ctypes.c_int),
                ('hInstApp', ctypes.c_void_p), ('lpIDList', ctypes.c_void_p),
                ('lpClass', ctypes.c_wchar_p), ('hkeyClass', ctypes.c_void_p),
                ('dwHotKey', ctypes.c_ulong), ('hIcon', ctypes.c_void_p),
                ('hProcess', ctypes.c_void_p),
            ]

        info = ShellExecuteInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
        info.lpVerb = 'runas'
        info.lpFile = str(PYTHON)
        info.lpParameters = subprocess.list2cmdline([str(TUNNEL_ENTRY)])
        info.lpDirectory = str(PROJECT)
        info.nShow = 0  # Keep the elevated daemon console hidden.
        shell = ctypes.windll.shell32
        shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
        shell.ShellExecuteExW.restype = ctypes.c_int
        if not shell.ShellExecuteExW(ctypes.byref(info)):
            error = ctypes.get_last_error()
            if error == 1223:
                raise RuntimeError('已取消管理员授权；共享隧道未启动，后台没有切换连接方式。')
            raise ctypes.WinError(error)
        try:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetProcessId.argtypes = [ctypes.c_void_p]
            kernel.GetProcessId.restype = ctypes.c_ulong
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle.restype = ctypes.c_int
            pid = kernel.GetProcessId(info.hProcess)
            if not pid:
                raise ctypes.WinError(ctypes.get_last_error())
            return pid
        finally:
            kernel.CloseHandle(info.hProcess)

    def _ensure_tunneld(self):
        if TUNNEL_STATE.exists():
            if self._tunneld_is_owned():
                if self._tunneld_healthy():
                    return
                raise RuntimeError('项目记录的共享隧道进程仍在运行但无响应；请彻底关闭后台后重试。')
            TUNNEL_STATE.unlink(missing_ok=True)
        if self._tunneld_healthy():
            raise RuntimeError('本机 49151 端口已有非本项目管理的 tunneld；为避免接管或关闭其他隧道，请先停止它。')
        process = next((p for p, entry in self.processes() if entry == 'tunneld_entry.py'), None)
        if process:
            raise RuntimeError('检测到未登记的项目 tunneld 进程；请彻底关闭后台后重试。')
        pid = self._launch_elevated_tunneld()
        try:
            self._store_tunneld_owner(pid)
        except (OSError, psutil.Error) as error:
            raise RuntimeError(f'管理员隧道已启动，但无法登记其进程：{error}') from error
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._tunneld_healthy():
                return
            if not psutil.pid_exists(pid):
                break
            time.sleep(0.25)
        tail = ''
        try:
            tail = (LOGS / 'tunneld.log').read_text(encoding='utf-8', errors='replace')[-1200:]
        except OSError:
            pass
        self._stop_tunneld()
        detail = f' 日志：{tail}' if tail else ''
        raise RuntimeError('共享隧道启动失败或未能在 30 秒内就绪。' + detail)

    def _stop_tunneld(self):
        if not TUNNEL_STATE.exists():
            return
        if not self._tunneld_is_owned():
            TUNNEL_STATE.unlink(missing_ok=True)
            return
        state = json.loads(TUNNEL_STATE.read_text(encoding='utf-8'))
        pid = int(state['pid'])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(TUNNEL_URL + '/shutdown', timeout=2):
                pass
        except (OSError, urllib.error.URLError):
            # The upstream endpoint may close its socket while delivering SIGINT.
            pass
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not psutil.pid_exists(pid):
                TUNNEL_STATE.unlink(missing_ok=True)
                return
            time.sleep(0.2)
        raise RuntimeError('已请求共享隧道退出，但管理员进程仍在运行；请查看 tunneld.log。')

    def stop(self):
        self._stop_tunneld()
        # Freeze parents before collecting descendants, so watchdogs cannot
        # replace viewers while the tree is being stopped. psutil retains
        # process creation times to protect against PID reuse.
        found = self.processes()
        if not found:
            return '后台已经彻底关闭。'
        suspended = {}
        targets = {}
        try:
            ordered = sorted(found, key=lambda row: row[1] != 'dashboard.py')
            for process, _ in ordered:
                try:
                    process.suspend()
                    suspended[process.pid] = process
                    targets[process.pid] = process
                except psutil.NoSuchProcess:
                    pass
            for _ in range(10):
                additions = []
                for process in list(targets.values()):
                    try:
                        additions.extend(child for child in process.children(recursive=True)
                                         if child.pid not in targets)
                    except psutil.NoSuchProcess:
                        pass
                if not additions:
                    break
                for child in additions:
                    try:
                        child.suspend()
                        suspended[child.pid] = child
                        targets[child.pid] = child
                    except psutil.NoSuchProcess:
                        pass
            else:
                raise RuntimeError('相关进程仍在变化，未执行关闭，请稍后重试。')
            for process in targets.values():
                try:
                    process.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(list(targets.values()), timeout=5)
            for process in alive:
                try:
                    process.kill()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs(alive, timeout=3)
            if self.started:
                self.started.poll()
            if alive or self.processes():
                raise RuntimeError('仍有相关进程未退出，请再次点击彻底关闭。')
            return '后台和相关子进程已全部关闭。'
        finally:
            for process in suspended.values():
                try:
                    process.resume()
                except psutil.NoSuchProcess:
                    pass


class ControlWindow:
    def __init__(self, root):
        self.root = root
        self.backend = Backend()
        self.results = queue.Queue()
        self.busy = False
        root.title('短信工作台 · 后台控制')
        root.geometry('550x300')
        root.minsize(550, 300)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='短信工作台后台', font=('Microsoft YaHei UI', 17, 'bold')).pack(anchor='w')
        self.status = tk.StringVar(value='正在检查后台…')
        ttk.Label(frame, textvariable=self.status, wraplength=495).pack(anchor='w', pady=(14, 18))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        self.start_button = ttk.Button(buttons, text='启动后台', command=lambda: self.run(self.backend.start))
        self.start_button.pack(side='left', ipadx=14, ipady=8)
        self.stop_button = ttk.Button(buttons, text='彻底关闭后台', command=lambda: self.run(self.backend.stop))
        self.stop_button.pack(side='left', padx=14, ipadx=14, ipady=8)
        self.message = tk.StringVar(value='启动后台时会请求一次管理员授权以运行 USB 共享隧道；关闭本窗口会保留后台。')
        ttk.Label(frame, textvariable=self.message, wraplength=495, foreground='#555555').pack(anchor='w', pady=(18, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def close(self):
        if self.busy:
            self.message.set('正在处理，请等待完成后关闭窗口。')
        else:
            self.root.destroy()

    def run(self, action):
        if self.busy:
            return
        self.busy = True
        self.start_button.state(['disabled'])
        self.stop_button.state(['disabled'])
        self.message.set('正在处理，请稍候…')
        def work():
            try:
                self.results.put((True, action()))
            except Exception as error:
                self.results.put((False, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            _, message = self.results.get_nowait()
            self.message.set(message)
            self.busy = False
            self.start_button.state(['!disabled'])
            self.stop_button.state(['!disabled'])
        except queue.Empty:
            pass
        if not self.busy:
            try:
                self.status.set(self.backend.status())
            except Exception as error:
                self.status.set(str(error))
        self.root.after(2000, self.poll)


def main(smoke_test=False):
    # Keep multiple desktop clicks from opening competing controllers.
    mutex = None
    if os.name == 'nt':
        import ctypes
        import hashlib
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        name = 'Local\\SmsBackendControl-' + hashlib.sha256(normalized(PROJECT).encode()).hexdigest()[:20]
        mutex = kernel.CreateMutexW(None, False, name)
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            ctypes.windll.user32.MessageBoxW(None, '后台控制窗口已经打开，请在任务栏中切换。', '短信工作台', 64)
            kernel.CloseHandle(mutex)
            return
    try:
        root = tk.Tk()
        ControlWindow(root)
        if smoke_test:
            root.after(2500, root.destroy)
        root.mainloop()
    finally:
        if mutex:
            kernel.CloseHandle(mutex)
