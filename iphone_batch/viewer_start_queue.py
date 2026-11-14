"""One bounded viewer startup at a time; stale or disabled requests never run."""
from collections import OrderedDict
import threading
import time
import logging


class ViewerStartQueue:
    def __init__(self,start,ready,allowed,failed,stopping,*,busy=lambda:False,
                 startup_timeout=180,busy_timeout=90,poll=.25):
        self.start,self.ready,self.allowed,self.failed=start,ready,allowed,failed
        self.stopping,self.busy=stopping,busy
        self.startup_timeout,self.busy_timeout,self.poll=startup_timeout,busy_timeout,poll
        self.lock=threading.Condition(threading.RLock())
        self.waiting=OrderedDict()
        self.generations={}
        self.current=None
        self.closed=False
        self.thread=threading.Thread(target=self.run,name='viewer-start-queue',daemon=True)
        self.thread.start()

    def pending(self,identifier):
        with self.lock:
            return identifier in self.waiting or (self.current is not None and self.current[0]==identifier
                and self.current[1]==self.generations.get(identifier,0))

    def valid(self,identifier,ticket):
        with self.lock:
            return not self.closed and not self.stopping.is_set() and ticket==self.generations.get(identifier,0)

    def request(self,device):
        identifier=device['udid']
        with self.lock:
            if self.closed or self.stopping.is_set() or self.pending(identifier):return False
            self.waiting[identifier]=(device,self.generations.get(identifier,0))
            self.lock.notify_all()
            return True

    def cancel(self,identifier):
        with self.lock:
            self.generations[identifier]=self.generations.get(identifier,0)+1
            self.waiting.pop(identifier,None)
            self.lock.notify_all()

    def run(self):
        while not self.stopping.is_set():
            with self.lock:
                self.lock.wait_for(lambda:self.closed or self.stopping.is_set() or self.waiting,timeout=.5)
                if self.closed or self.stopping.is_set():return
                if not self.waiting:continue
                identifier,(device,ticket)=self.waiting.popitem(last=False)
                self.current=(identifier,ticket)
            valid=lambda:self.valid(identifier,ticket) and self.allowed(device)
            try:
                deadline=time.monotonic()+self.busy_timeout
                while valid() and self.busy():
                    if time.monotonic()>=deadline:raise TimeoutError('CPU 持续繁忙，暂未接入此台')
                    self.stopping.wait(self.poll)
                if not valid() or self.start(device,ticket) is False:continue
                deadline=time.monotonic()+self.startup_timeout
                while valid():
                    if self.ready(device):break
                    if time.monotonic()>=deadline:raise TimeoutError('该台画面准备超时，未继续并行启动')
                    self.stopping.wait(self.poll)
            except Exception as error:
                if valid():
                    try:self.failed(device,error,ticket)
                    except Exception as cleanup_error:
                        logging.getLogger(__name__).warning('Viewer startup cleanup failed: %s',type(cleanup_error).__name__)
            finally:
                with self.lock:
                    if self.current==(identifier,ticket):self.current=None
                    self.lock.notify_all()

    def close(self):
        with self.lock:
            self.closed=True
            self.waiting.clear()
            self.lock.notify_all()
        self.thread.join(timeout=3)
