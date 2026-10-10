"""Bounded parallel notification checks with per-device operation locks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
import time


class NotificationMonitor:
    def __init__(self, devices, phone_lock, lease, scan, ready, stopping, interval=30,
                 lock_for=None, workers=4):
        self.devices=devices
        self.phone_lock=phone_lock
        self.lease=lease
        self.scan=scan
        self.ready=ready
        self.stopping=stopping
        self.interval=interval
        self.lock_for=lock_for or (lambda device: self.phone_lock)
        self.workers=workers
        self.lock=threading.RLock()
        now=time.monotonic()
        self.states={d['udid']:{'state':'waiting','last_checked':None,'pending_contacts':0,
            'items':[],'protected':False,'next_due':now+5+i*.3,'error':None} for i,d in enumerate(devices)}

    def protect(self, device, protected):
        with self.lock:
            if device not in self.states:raise ValueError('未知手机')
            self.states[device]['protected']=protected

    def snapshot(self, device):
        with self.lock:
            state=self.states[device]
            return {**{k:v for k,v in state.items() if k!='next_due'},
                    'interval_seconds':self.interval,'parallel_limit':self.workers}

    def record(self, device, result):
        with self.lock:
            self.states[device].update(state='checked',last_checked=datetime.now(timezone.utc).isoformat(),
                items=result['items'],error=None,
                pending_contacts=len({r.get('phone_number') or r.get('sender') for r in result['items']}),
                next_due=time.monotonic()+self.interval)

    def acknowledge(self, device, identifier):
        with self.lock:
            state=self.states[device]
            state['items']=[r for r in state['items'] if r['id']!=identifier]
            state['pending_contacts']=len({r.get('phone_number') or r.get('sender') for r in state['items']})

    def tick(self, now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            due=[d for d in self.devices if self.states[d['udid']]['next_due']<=now
                 and not self.states[d['udid']]['protected']
                 and self.states[d['udid']]['state']!='scanning']
            for device in sorted(due,key=lambda d:self.states[d['udid']]['next_due']):
                operation_lock=self.lock_for(device['udid'])
                if operation_lock.acquire(blocking=False):
                    state=self.states[device['udid']]
                    state['state']='scanning'
                    break
            else:return False
        started=time.monotonic()
        try:
            if not self.ready(device):raise ValueError('手机投屏尚未就绪，稍后重查')
            with self.lease(device['udid']):
                result=self.scan(device['udid'],f"http://127.0.0.1:{device['port']}")
            self.record(device['udid'],result)
        except Exception as exc:
            with self.lock:
                state.update(state='paused',error=str(exc))
        finally:
            with self.lock:
                state['next_due']=time.monotonic()+self.interval
                state['scan_seconds']=round(time.monotonic()-started,2)
            operation_lock.release()
        return True

    def run(self):
        with ThreadPoolExecutor(max_workers=self.workers,thread_name_prefix='notifications') as pool:
            pending=set()
            while not self.stopping.wait(.5):
                finished={future for future in pending if future.done()}
                for future in finished:
                    future.result()
                pending-=finished
                for _ in range(self.workers-len(pending)):
                    pending.add(pool.submit(self.tick))
