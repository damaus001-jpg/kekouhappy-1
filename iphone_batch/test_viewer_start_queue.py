import threading
import time
import unittest
from unittest.mock import Mock
from viewer_start_queue import ViewerStartQueue


def until(predicate):
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.005)
    raise AssertionError('queue did not make expected progress')


class ViewerStartTests(unittest.TestCase):
    def queue(self,start,ready,**options):
        stopping=threading.Event()
        queue=ViewerStartQueue(start,ready,lambda d:True,options.pop('failed',Mock()),stopping,
            poll=.005,**options)
        self.addCleanup(queue.close)
        self.addCleanup(stopping.set)
        return queue

    def test_only_one_start_until_previous_video_is_ready(self):
        started=[]
        ready=set()
        queue=self.queue(lambda d,t:started.append(d['udid']),lambda d:d['udid'] in ready)
        queue.request({'udid':'one'});queue.request({'udid':'two'})
        until(lambda:len(started)==1)
        time.sleep(.03)
        self.assertEqual(started,['one'])
        ready.add('one')
        until(lambda:len(started)==2)
        self.assertEqual(started,['one','two'])

    def test_cancel_while_waiting_for_cpu_never_starts_disabled_entry(self):
        busy=threading.Event();busy.set()
        started=[]
        queue=self.queue(lambda d,t:started.append(d['udid']),lambda d:True,busy=busy.is_set)
        queue.request({'udid':'off'})
        until(lambda:queue.current is not None)
        queue.cancel('off')
        queue.request({'udid':'on'})
        busy.clear()
        until(lambda:bool(started))
        self.assertEqual(started,['on'])

    def test_cancel_then_reenable_does_not_lose_new_request(self):
        started=[];entered=threading.Event();release=threading.Event()
        def ready(device):
            entered.set();release.wait(1);return True
        queue=self.queue(lambda d,t:started.append(t),ready)
        queue.request({'udid':'one'});self.assertTrue(entered.wait(1))
        queue.cancel('one')
        self.assertTrue(queue.request({'udid':'one'}))
        release.set();until(lambda:len(started)==2)
        self.assertEqual(started,[0,1])

    def test_failed_start_advances_queue_with_bounded_error_callback(self):
        started=[];failed=Mock()
        def start(device,ticket):
            started.append(device['udid'])
            if device['udid']=='bad':raise OSError('simulated startup failure')
        queue=self.queue(start,lambda d:True,failed=failed)
        queue.request({'udid':'bad'});queue.request({'udid':'good'})
        until(lambda:len(started)==2)
        self.assertEqual(started,['bad','good'])
        until(lambda:failed.call_count==1)
        self.assertEqual(failed.call_args.args[0]['udid'],'bad')

    def test_timeout_stops_current_before_starting_next(self):
        order=[]
        queue=self.queue(lambda d,t:order.append('start-'+d['udid']),lambda d:d['udid']=='two',
            failed=lambda d,e,t:order.append('stop-'+d['udid']),startup_timeout=.03)
        queue.request({'udid':'one'});queue.request({'udid':'two'})
        until(lambda:'start-two' in order)
        self.assertEqual(order,['start-one','stop-one','start-two'])

    def test_close_discards_pending_work(self):
        started=[]
        queue=self.queue(lambda d,t:started.append(d['udid']),lambda d:False)
        queue.request({'udid':'one'});queue.request({'udid':'two'})
        until(lambda:bool(started))
        queue.close()
        self.assertEqual(started,['one'])
        self.assertFalse(queue.request({'udid':'three'}))

    def test_initial_setup_can_finish_after_normal_reconnect_deadline(self):
        started=[];failed=Mock()
        queue=self.queue(lambda d,t:started.append(time.monotonic()),
            lambda d:bool(started) and time.monotonic()-started[-1]>.08,
            failed=failed,startup_timeout=.02,initial_startup_timeout=.3)
        queue.request({'udid':'new'})
        until(lambda:'new' in queue.ready_devices)
        self.assertFalse(failed.called)

    def test_previously_ready_device_uses_short_timeout_on_reconnect(self):
        ready=threading.Event();ready.set();failed=Mock()
        queue=self.queue(lambda d,t:None,lambda d:ready.is_set(),failed=failed,
            startup_timeout=.02,initial_startup_timeout=.8)
        device={'udid':'known'}
        queue.request(device)
        until(lambda:'known' in queue.ready_devices and not queue.pending('known'))
        ready.clear()
        queue.request(device)
        until(lambda:failed.called)
        self.assertIn('0.02秒',str(failed.call_args.args[1]))
