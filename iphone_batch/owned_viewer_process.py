"""Stop one verified viewer tree without racing its startup or other devices."""
import os
from pathlib import Path
import psutil


def stop_tree(pid, expected_script, device):
    expected_script=Path(expected_script).resolve()
    held={}
    try:
        parent=psutil.Process(pid)
        command=parent.cmdline()
        if (len(command)<2 or Path(command[1]).resolve()!=expected_script or device not in command):
            raise RuntimeError('设备进程身份变化，已取消停止')
        parent.suspend()
        held[parent.pid]=parent
        for _ in range(10):
            pending=[]
            for child in parent.children(recursive=True):
                try:
                    if child.name().lower()=='conhost.exe':
                        system_host=Path(os.environ.get('WINDIR',r'C:\Windows'))/'System32'/'conhost.exe'
                        if Path(child.exe()).resolve()!=system_host.resolve():raise RuntimeError('控制台进程身份变化')
                        continue
                    if child.pid not in held:pending.append(child)
                except psutil.NoSuchProcess:pass
            if not pending:break
            for child in pending:
                try:
                    command=child.cmdline()
                    script=Path(command[1]).resolve() if len(command)>1 else None
                    if script is None or script.parent!=expected_script.parent or script.name not in ('controller.py','pmd_entry.py'):
                        raise RuntimeError('设备子进程身份变化，已取消停止')
                    child.suspend()
                    held[child.pid]=child
                except psutil.NoSuchProcess:pass
        else:raise RuntimeError('设备启动进程仍在变化，已取消停止')
        for process in reversed(list(held.values())):
            try:process.terminate()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(list(held.values()),timeout=3)
        for process in alive:
            try:process.kill()
            except psutil.NoSuchProcess:pass
        _,alive=psutil.wait_procs(alive,timeout=2)
        if alive:raise RuntimeError('该台仍有进程未退出，断开未完成')
    except psutil.NoSuchProcess:pass
    finally:
        for process in held.values():
            try:process.resume()
            except psutil.NoSuchProcess:pass
