"""Cancelable subprocesses used only for background notification scans."""
import contextlib
from collections import deque
import json
from pathlib import Path
import queue
import subprocess
import threading
import uuid

from notification_worker import MAX_LINE


class BannerWorker:
    def __init__(self, command, terminate, **kwargs):
        self.command = tuple(command)
        self.terminate = terminate
        self.lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.closed = False
        self.responses = queue.Queue(maxsize=4)
        self.stderr = deque(maxlen=16)
        kwargs.setdefault('encoding', 'utf-8')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=1, **kwargs)
        self.readers = [threading.Thread(target=target, daemon=True) for target in
                        (self._read_stdout, self._read_stderr)]
        for reader in self.readers:
            reader.start()

    def _read_stdout(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE)
                if not line:
                    break
                try:
                    self.responses.put(line, timeout=.5)
                except queue.Full:
                    return
        finally:
            with contextlib.suppress(queue.Full):
                self.responses.put_nowait(None)

    def _read_stderr(self):
        while line := self.process.stderr.readline(2048):
            self.stderr.append(line[-512:])

    def request(self, timeout):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise RuntimeError('横幅读取进程已退出')
            identifier = uuid.uuid4().hex
            self.process.stdin.write(json.dumps({'request_id': identifier}) + '\n')
            self.process.stdin.flush()
            try:
                line = self.responses.get(timeout=timeout)
            except queue.Empty:
                raise subprocess.TimeoutExpired(self.command, timeout) from None
            if line is None:
                raise RuntimeError('横幅读取进程未返回结果')
            response = json.loads(line)
            if (not isinstance(response, dict) or response.get('request_id') != identifier
                    or not isinstance(response.get('result'), dict)):
                raise ValueError('横幅读取回执不匹配，已停止该进程')
            result = response['result']
            return subprocess.CompletedProcess(self.command, 1 if result.get('error') else 0,
                json.dumps(result, ensure_ascii=True), ''.join(list(self.stderr)))

    def close(self):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
            self.terminate(self.process, self.command)
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=3)
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                with contextlib.suppress(OSError, ValueError):
                    stream.close()
            for reader in self.readers:
                reader.join(timeout=.5)


class NotificationRunner:
    def __init__(self):
        self.enabled = True
        self.lock = threading.RLock()
        self.jobs = {}
        self.workers = {}
        self.worker_starts = 0
        self.worker_reuses = 0

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
            workers = list(self.workers.values()) if not enabled else []
            if not enabled:
                self.workers.clear()
        for worker in workers:
            worker.close()
        worker_ids = {worker.process.pid for worker in workers}
        for job in jobs:
            if job['process'].pid not in worker_ids:
                self.terminate(job['process'], job['command'])
        return len(jobs)

    @staticmethod
    def banner_command(device, command):
        expected = Path(__file__).resolve().with_name('native_workspace.py')
        try:
            return (len(command) > 2 and Path(command[1]).resolve() == expected
                    and command[command.index('--action') + 1] in ('banner','badge')
                    and command[command.index('--device') + 1] == device
                    and '--banner-worker' not in command)
        except (ValueError, IndexError, TypeError):
            return False

    def _run_banner(self, device, command, timeout, **kwargs):
        worker_command = [*command, '--banner-worker']
        with self.lock:
            if not self.enabled:
                raise ValueError('自动遍历已关闭')
            if device in self.jobs:
                raise ValueError('该设备正在读取横幅，请稍候')
            worker = self.workers.get(device)
            if worker and (worker.process.poll() is not None or worker.command != tuple(worker_command)):
                worker.close()
                self.workers.pop(device, None)
                worker = None
            if worker is None:
                worker = BannerWorker(worker_command, self.terminate, **kwargs)
                self.workers[device] = worker
                self.worker_starts += 1
            else:
                self.worker_reuses += 1
            job = {'process': worker.process, 'command': worker.command, 'cancelled': False}
            self.jobs[device] = job
        try:
            result = worker.request(timeout)
            if job['cancelled']:
                raise ValueError('自动遍历已关闭')
            if result.returncode:
                # Discard the process after a native connection error. A future
                # scheduled read may reconnect; this read is never replayed.
                with self.lock:
                    if self.workers.get(device) is worker:
                        self.workers.pop(device)
                worker.close()
            return result
        except Exception:
            with self.lock:
                if self.workers.get(device) is worker:
                    self.workers.pop(device)
            worker.close()
            if job['cancelled']:
                raise ValueError('自动遍历已关闭') from None
            raise
        finally:
            with self.lock:
                if self.jobs.get(device) is job:
                    del self.jobs[device]

    def retire(self, device):
        """Release an idle cached reader before reconnect/disconnect."""
        with self.lock:
            worker = self.workers.pop(device, None)
            job = self.jobs.get(device)
            if job and worker and job['process'] is worker.process:
                job['cancelled'] = True
        if worker:
            worker.close()

    def run(self, device, command, timeout=130, **kwargs):
        if self.banner_command(device, command):
            return self._run_banner(device, command, timeout, **kwargs)
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
