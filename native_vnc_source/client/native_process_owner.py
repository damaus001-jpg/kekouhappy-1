"""Own every client subprocess across concurrent startup and shutdown."""
import threading
import uuid
import ctypes
from ctypes import wintypes
import psutil


class WindowsJob:
    def __init__(self):
        import win32job
        self.api=win32job
        self.handle=win32job.CreateJobObject(None,'Local\\NativeVNCWorkbench-'+uuid.uuid4().hex)
        info=win32job.QueryInformationJobObject(self.handle,win32job.JobObjectExtendedLimitInformation)
        info['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(self.handle,win32job.JobObjectExtendedLimitInformation,info)

    def add(self,pid):
        import win32api
        handle=win32api.OpenProcess(0x0100|0x0001|0x1000,False,pid)
        try:self.api.AssignProcessToJobObject(self.handle,handle)
        finally:handle.Close()

    def close(self):
        if self.handle is not None:
            self.handle.Close()
            self.handle=None


def terminate_tree(pid):
    try:
        parent=psutil.Process(pid)
        children=parent.children(recursive=True)
        for child in reversed(children):
            try:child.kill()
            except psutil.Error:pass
        parent.kill()
    except psutil.Error:pass


def resume_process(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenThread.restype=wintypes.HANDLE
    kernel.ResumeThread.argtypes=[wintypes.HANDLE]
    kernel.ResumeThread.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    for thread in psutil.Process(pid).threads():
        handle=kernel.OpenThread(0x0002,False,thread.id)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        try:
            if kernel.ResumeThread(handle)==0xffffffff:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:kernel.CloseHandle(handle)


class ProcessOwner:
    def __init__(self,job=None,terminate=terminate_tree):
        self.lock=threading.RLock()
        self.closed=False
        self.processes={}
        self.unassigned=set()
        self.identities={}
        self.assignment_errors={}
        self.job_error=None
        self.tags={}
        self.blocked_tags=set()
        self.generations={}
        self.terminate=terminate
        try:self.job=job if job is not None else WindowsJob()
        except Exception as exc:
            self.job=None
            self.job_error=str(exc)

    def _register(self,pid,process=None,tag=None):
        self.processes[pid]=process
        self.tags[pid]=tag
        try:self.identities[pid]=psutil.Process(pid).create_time()
        except psutil.Error:pass
        try:
            if self.job is None:raise RuntimeError('Job object unavailable')
            self.job.add(pid)
        except Exception as exc:
            self.assignment_errors[pid]=str(exc)
            try:
                self.identities[pid]=psutil.Process(pid).create_time()
                self.unassigned.add(pid)
            except psutil.Error:pass

    def ticket(self,tag):
        with self.lock:return self.generations.get(tag,0)

    def _check(self,tag,ticket):
        if self.closed:raise RuntimeError('客户端正在关闭，取消后台启动')
        if tag in self.blocked_tags:raise RuntimeError('此设备已手动断开')
        if tag is not None and ticket is not None and ticket!=self.generations.get(tag,0):
            raise RuntimeError('此设备的旧启动任务已取消')

    def spawn(self,factory,*,suspended=False,tag=None,ticket=None):
        with self.lock:
            self._check(tag,ticket)
            process=factory()
            self._register(process.pid,process,tag)
            if suspended:
                try:resume_process(process.pid)
                except Exception:
                    self.terminate(process.pid)
                    raise
            return process

    def adopt(self,pid,*,tag=None,ticket=None):
        with self.lock:
            self._check(tag,ticket)
            self._register(pid,tag=tag)

    def stop_tag(self,tag):
        with self.lock:
            self.blocked_tags.add(tag)
            self.generations[tag]=self.generations.get(tag,0)+1
            for pid in [p for p,t in self.tags.items() if t==tag]:
                process=self.processes.get(pid)
                try:
                    live=(process.poll() is None) if process is not None else (psutil.Process(pid).create_time()==self.identities.get(pid))
                    if live:self.terminate(pid)
                except psutil.Error:pass
                self.forget(pid)

    def resume_tag(self,tag):
        with self.lock:
            if self.closed:raise RuntimeError('客户端正在关闭')
            self.blocked_tags.discard(tag)

    def forget(self,pid):
        with self.lock:
            self.processes.pop(pid,None)
            self.unassigned.discard(pid)
            self.identities.pop(pid,None)
            self.assignment_errors.pop(pid,None)
            self.tags.pop(pid,None)

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            if self.job is not None:self.job.close()
            for pid in self.unassigned:
                try:
                    if psutil.Process(pid).create_time()==self.identities[pid]:
                        self.terminate(pid)
                except psutil.Error:pass
            self.processes.clear()
            self.unassigned.clear()
            self.identities.clear()
            self.tags.clear()
