"""Serial, bounded reads of Messages icon badges on unselected live devices."""
from __future__ import annotations

import threading
import time


class UnreadBadgeMonitor:
    def __init__(self, devices, scan, ready, stopping, selected, lock_for, *, interval=2):
        self.devices=list(devices)
        self.scan=scan
        self.ready=ready
        self.stopping=stopping
        self.selected=selected
        self.lock_for=lock_for
        self.interval=max(1,float(interval))
        self.lock=threading.RLock()
        self.states={d['udid']:{'state':'waiting','count':None,'updated_at':None,'error':None}
                     for d in devices}
        self.cursor=0

    @staticmethod
    def _number(device):
        try:return int(device.get('number',device.get('name','').split()[-1]))
        except (TypeError,ValueError,IndexError):return 10**9

    def snapshot(self, device):
        with self.lock:
            row=self.states.get(device,{'state':'waiting','count':None,'updated_at':None,'error':None})
            return dict(row)

    def update_devices(self, devices):
        with self.lock:
            self.devices=list(devices)
            for d in devices:
                self.states.setdefault(d['udid'],{'state':'waiting','count':None,'updated_at':None,'error':None})

    def tick(self):
        with self.lock:
            devices=sorted(self.devices,key=self._number)
            if not devices:return False
            start=self.cursor%len(devices)
            ordered=devices[start:]+devices[:start]
            candidate=next((d for d in ordered if d['udid']!=self.selected()
                and self.ready(d)),None)
            if candidate is None:return False
            self.cursor=(devices.index(candidate)+1)%len(devices)
            state=self.states[candidate['udid']]
            state.update(state='reading',error=None)
        lock=self.lock_for(candidate['udid'])
        if not lock.acquire(blocking=False):
            with self.lock:state.update(state='waiting',error=None)
            return False
        try:
            # Recheck immediately before connecting. Selection always wins.
            if candidate['udid']==self.selected() or not self.ready(candidate):
                with self.lock:state.update(state='waiting',error=None)
                return True
            result=self.scan(candidate['udid'],f"http://127.0.0.1:{candidate['port']}")
            count=result.get('unread_count')
            if (result.get('source')!='app_icon_badge' or type(count) is not int or count<0):
                raise ValueError(result.get('error') or '未读角标元素未确认')
            with self.lock:state.update(state='read',count=count,updated_at=result.get('observed_at'),error=None)
        except Exception as exc:
            with self.lock:state.update(state='unavailable',error=str(exc)[:240])
        finally:lock.release()
        return True

    def run(self):
        while not self.stopping.is_set():
            attempted=self.tick()
            self.stopping.wait(self.interval if attempted else .5)
