"""One bounded viewer startup at a time; stale or disabled requests never run."""
from collections import OrderedDict
import threading
import time
import logging


class ViewerStartQueue:
    def __init__(self,start,ready,allowed,failed,stopping,*,busy=lambda:False,
                 startup_timeout=60,initial_startup_timeout=None,busy_timeout=90,retry_delay=30,poll=.25):
        self.start,self.ready,self.allowed,self.failed=start,ready,allowed,failed
        self.stopping,self.busy=stopping,busy
        self.startup_timeout,self.busy_timeout,self.retry_delay,self.poll=startup_timeout,busy_timeout,retry_delay,poll
        self.initial_startup_timeout=initial_startup_timeout if initial_startup_timeout is not None else startup_timeout
        self.ready_devices=set()
        self.lock=threading.Condition(threading.RLock())
        self.waiting=OrderedDict()
        self.generations={}
        self.terminal=set()
        self.current=None
        self.closed=False
        self.thread=threading.Thread(target=self.run,name='viewer-start-queue',daemon=True)
        self.thread.start()

    def pending(self,identifier):
        with self.lock:
            return identifier in self.waiting or (self.current is not None and self.current[0]==identifier
                and self.current[1]==self.generations.get(identifier,0))

    def attempt(self,identifier):
        with self.lock:
            if self.current is not None and self.current[0]==identifier:
                return self.current[2]
            queued=self.waiting.get(identifier)
            return queued[2] if queued else None

    def terminal_failure(self,identifier):
        with self.lock:
            return identifier in self.terminal

    def valid(self,identifier,ticket):
        with self.lock:
            return not self.closed and not self.stopping.is_set() and ticket==self.generations.get(identifier,0)

    def request(self,device):
        identifier=device['udid']
        with self.lock:
            if self.closed or self.stopping.is_set() or self.pending(identifier):return False
            self.terminal.discard(identifier)
            self.waiting[identifier]=(device,self.generations.get(identifier,0),0,0.0)
            self.lock.notify_all()
            return True

    def cancel(self,identifier):
        with self.lock:
            self.generations[identifier]=self.generations.get(identifier,0)+1
            self.waiting.pop(identifier,None)
            self.terminal.discard(identifier)
            self.lock.notify_all()

    def discard_ready(self,identifier):
        """Forget a previously ready device so its next first attempt uses the
        initial startup timeout again (phone reboot, USB re-plug cold start)."""
        with self.lock:
            self.ready_devices.discard(identifier)

    def run(self):
        while not self.stopping.is_set():
            with self.lock:
                while not self.closed and not self.stopping.is_set():
                    if not self.waiting:
                        self.lock.wait(timeout=.5)
                        continue
                    now=time.monotonic()
                    due_entry=next(((key,value) for key,value in self.waiting.items() if value[3]<=now),None)
                    if due_entry is not None:
                        identifier,(device,ticket,attempt,_due)=due_entry
                        self.waiting.pop(identifier,None)
                        self.current=(identifier,ticket,attempt)
                        break
                    next_due=min(value[3] for value in self.waiting.values())
                    self.lock.wait(timeout=min(.5,max(.01,next_due-now)))
                if self.closed or self.stopping.is_set():return
            valid=lambda:self.valid(identifier,ticket) and self.allowed(device)
            failed=False
            try:
                deadline=time.monotonic()+self.busy_timeout
                while valid() and self.busy():
                    if time.monotonic()>=deadline:raise TimeoutError('CPU 持续繁忙，暂未接入此台')
                    self.stopping.wait(self.poll)
                if not valid() or self.start(device,ticket) is False:continue
                # First-time setup includes image preparation before a frame can
                # exist. Later reconnects and the one retry stay bounded normally.
                timeout=self.initial_startup_timeout if attempt==0 and identifier not in self.ready_devices else self.startup_timeout
                deadline=time.monotonic()+timeout
                while valid():
                    if self.ready(device):
                        self.ready_devices.add(identifier)
                        break
                    if time.monotonic()>=deadline:raise TimeoutError(f'连接超过{timeout:g}秒，已跳过此台')
                    self.stopping.wait(self.poll)
            except Exception as error:
                if valid():
                    failed=True
                    try:self.failed(device,error,ticket)
                    except Exception as cleanup_error:
                        logging.getLogger(__name__).warning('Viewer startup cleanup failed: %s',type(cleanup_error).__name__)
            finally:
                with self.lock:
                    if self.current==(identifier,ticket,attempt):self.current=None
                    if failed and self.valid(identifier,ticket) and self.allowed(device):
                        if attempt==0:
                            self.waiting[identifier]=(device,ticket,1,time.monotonic()+self.retry_delay)
                        else:
                            self.terminal.add(identifier)
                    self.lock.notify_all()

    def close(self):
        with self.lock:
            self.closed=True
            self.waiting.clear()
            self.lock.notify_all()
        self.thread.join(timeout=3)
