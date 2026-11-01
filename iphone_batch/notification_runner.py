"""Cancelable subprocesses used only for background notification scans."""
import contextlib
import subprocess
import threading


class NotificationRunner:
    def __init__(self):
        self.enabled = True
        self.lock = threading.RLock()
        self.jobs = {}

    @staticmethod
    def terminate(process, command):
        import psutil
        if process.poll() is not None:
            return
        try:
            parent = psutil.Process(process.pid)
            if parent.cmdline()[1:] != list(command)[1:]:
                raise RuntimeError('遍历进程身份变化，未停止其他进程')
            parent.suspend()
            try:
                children = parent.children(recursive=True)
                for child in reversed(children):
                    with contextlib.suppress(psutil.NoSuchProcess):
                        if child.name().lower().startswith('python'):
                            child.terminate()
                with contextlib.suppress(psutil.NoSuchProcess):
                    parent.terminate()
            except Exception:
                with contextlib.suppress(psutil.NoSuchProcess):
                    parent.resume()
                raise
        except psutil.NoSuchProcess:
            pass

    def set_enabled(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('无效的遍历开关状态')
        with self.lock:
            self.enabled = enabled
            jobs = list(self.jobs.values()) if not enabled else []
            for job in jobs:
                job['cancelled'] = True
        for job in jobs:
            self.terminate(job['process'], job['command'])
        return len(jobs)

    def run(self, device, command, timeout=130, **kwargs):
        with self.lock:
            if not self.enabled:
                raise ValueError('自动遍历已关闭')
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
            job = {'process': process, 'command': tuple(command), 'cancelled': False}
            self.jobs[device] = job
        try:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.terminate(process, command)
                process.communicate(timeout=5)
                raise
            if job['cancelled']:
                raise ValueError('自动遍历已关闭')
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            with self.lock:
                if self.jobs.get(device) is job:
                    del self.jobs[device]
