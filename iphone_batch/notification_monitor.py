"""Bounded parallel notification checks with per-device operation locks."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import threading
import time


class NotificationMonitor:
    def __init__(self, devices, phone_lock, lease, scan, ready, stopping, interval=0,
                 lock_for=None, workers=4, manual_device=None, on_new_cards=None):
        self.devices=devices
        self.phone_lock=phone_lock
        self.lease=lease
        self.scan=scan
        self.ready=ready
        self.stopping=stopping
        self.interval=interval
        self.lock_for=lock_for or (lambda device: self.phone_lock)
        self.workers=workers
        self.manual_device=manual_device or (lambda: None)
        self.on_new_cards=on_new_cards
        self.lock=threading.RLock()
        self.queue_order={d['udid']:i for i,d in enumerate(devices)}
        self.next_order=len(devices)
        now=time.monotonic()
        self.states={d['udid']:{'state':'waiting','last_checked':None,'pending_contacts':0,
            'items':[],'protected':False,'next_due':now,'error':None} for d in devices}

    def protect(self, device, protected):
        with self.lock:
            if device not in self.states:raise ValueError('未知手机')
            self.states[device]['protected']=protected

    def snapshot(self, device):
        with self.lock:
            state=self.states[device]
            return {**{k:v for k,v in state.items() if k!='next_due'},
                    'card_count':len(state['items']),
                    'manual_control':device==self.manual_device(),
                    'interval_seconds':self.interval,'parallel_limit':self.workers}

    def record(self, device, result):
        with self.lock:
            previous={row.get('id') for row in self.states[device]['items']}
            new_cards=any(row.get('id') not in previous for row in result['items'])
            self.states[device].update(state='checked',last_checked=datetime.now(timezone.utc).isoformat(),
                items=result['items'],error=None,
                pending_contacts=len({r.get('phone_number') or r.get('sender') for r in result['items']}),
                next_due=time.monotonic()+self.interval)
        if new_cards and self.on_new_cards:
            try:
                self.on_new_cards(device)
            except Exception:
                # Audio failure must not discard a successful notification scan.
                pass

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
                 and d['udid']!=self.manual_device()
                 and self.states[d['udid']]['state']!='scanning']
            for device in sorted(due,key=lambda d:self.queue_order[d['udid']]):
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
                self.queue_order[device['udid']]=self.next_order
                self.next_order+=1
            operation_lock.release()
        return True

    def run(self):
        with ThreadPoolExecutor(max_workers=self.workers,thread_name_prefix='notifications') as pool:
            pending=set()
            while not self.stopping.is_set():
                for _ in range(self.workers-len(pending)):
                    pending.add(pool.submit(self.tick))
                finished,pending=wait(pending,timeout=.1,return_when=FIRST_COMPLETED)
                attempted=False
                for future in finished:
                    attempted=future.result() or attempted
                if finished and not attempted:
                    self.stopping.wait(.1)
