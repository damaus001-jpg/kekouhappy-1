from contextlib import contextmanager
import threading
import unittest
from unittest.mock import patch
from notification_monitor import NotificationMonitor
from dashboard import FocusManager


class MonitorTests(unittest.TestCase):
    def make_monitor(self, scan=None):
        self.calls=[]
        devices=[{'udid':f'phone{i}','port':8080+i} for i in range(10)]
        @contextmanager
        def lease(device):
            self.calls.append(('lease',device))
            yield
            self.calls.append(('restore',device))
        def discover(device,base):
            self.calls.append(('scan',device))
            return {'items':[{'id':'a','phone_number':'+123'},{'id':'b','phone_number':'+123'}]}
        with patch('notification_monitor.time.monotonic',return_value=100):
            return NotificationMonitor(devices,threading.Lock(),lease,scan or discover,
                                       lambda d:True,threading.Event())

    def test_ten_devices_repeat_immediately_in_fair_order_even_with_equal_times(self):
        monitor=self.make_monitor()
        with patch('notification_monitor.time.monotonic',return_value=140):
            for _ in range(20):self.assertTrue(monitor.tick(now=140))
        self.assertEqual([device for action,device in self.calls if action=='scan'],[f'phone{i}' for i in range(10)]*2)
        self.assertEqual(monitor.snapshot('phone0')['interval_seconds'],0)
        self.assertEqual(monitor.snapshot('phone0')['pending_contacts'],1)
        self.assertEqual(monitor.snapshot('phone0')['state'],'checked')

    def test_first_check_has_no_startup_delay(self):
        monitor=self.make_monitor()
        with patch('notification_monitor.time.monotonic',return_value=100):
            self.assertTrue(monitor.tick(now=100))
        self.assertEqual([device for action,device in self.calls if action=='scan'],['phone0'])

    def test_sound_only_on_new_cards_including_replacement_at_same_count(self):
        monitor=self.make_monitor()
        sounded=[]
        monitor.on_new_cards=sounded.append
        monitor.record('phone0',{'items':[{'id':'a'}]})
        monitor.record('phone0',{'items':[{'id':'a'}]})
        self.assertEqual(sounded,['phone0'])
        monitor.record('phone0',{'items':[{'id':'b'}]})
        monitor.record('phone1',{'items':[{'id':'b'}]})
        self.assertEqual(sounded,['phone0','phone0','phone1'])
        monitor.record('phone0',{'items':[]})
        self.assertEqual(len(sounded),3)

    def test_audio_failure_does_not_lose_card_count(self):
        monitor=self.make_monitor()
        monitor.on_new_cards=lambda device:(_ for _ in ()).throw(RuntimeError('audio unavailable'))
        monitor.record('phone0',{'items':[{'id':'a'}]})
        self.assertEqual(monitor.snapshot('phone0')['card_count'],1)
        self.assertEqual(monitor.snapshot('phone0')['state'],'checked')

    def test_run_refills_workers_until_stopped(self):
        scanned=[]
        def scan(device,base):
            scanned.append(device)
            if len(scanned)>=8:monitor.stopping.set()
            return {'items':[]}
        monitor=self.make_monitor(scan)
        monitor.devices=monitor.devices[:2]
        monitor.workers=1
        runner=threading.Thread(target=monitor.run,daemon=True)
        runner.start();runner.join(timeout=3)
        monitor.stopping.set()
        self.assertFalse(runner.is_alive())
        self.assertEqual(scanned,['phone0','phone1']*4)

    def test_draft_protection_and_busy_phone_skip_background_scanning(self):
        monitor=self.make_monitor()
        for device in monitor.states:monitor.protect(device,True)
        self.assertFalse(monitor.tick(now=140))
        monitor.protect('phone0',False)
        monitor.phone_lock.acquire()
        try:self.assertFalse(monitor.tick(now=140))
        finally:monitor.phone_lock.release()
        self.assertEqual(self.calls,[])

    def test_manual_phone_is_skipped_and_cards_from_same_sender_are_counted(self):
        monitor=self.make_monitor()
        selected=['phone0']
        monitor.manual_device=lambda:selected[0]
        with patch('notification_monitor.time.monotonic',return_value=140):
            self.assertTrue(monitor.tick(now=140))
        self.assertEqual([device for action,device in self.calls if action=='scan'],['phone1'])
        self.assertTrue(monitor.snapshot('phone0')['manual_control'])
        self.assertEqual(monitor.snapshot('phone1')['card_count'],2)
        selected[0]='phone1'
        with patch('notification_monitor.time.monotonic',return_value=140):
            self.assertTrue(monitor.tick(now=140))
        self.assertEqual(monitor.snapshot('phone0')['card_count'],2)
        monitor.record('phone0',{'items':[]})
        self.assertEqual(monitor.snapshot('phone0')['card_count'],0)

    def test_scan_failure_preserves_pending_state_and_has_an_error(self):
        monitor=self.make_monitor(scan=lambda *args:(_ for _ in ()).throw(ValueError('offline')))
        with patch('notification_monitor.time.monotonic',return_value=100):
            monitor.record('phone0',{'items':[{'id':'a','phone_number':'+123'}]})
        with patch('notification_monitor.time.monotonic',return_value=400):
            for _ in range(10):monitor.tick(now=400)
        self.assertEqual(monitor.snapshot('phone0')['pending_contacts'],1)
        self.assertEqual(monitor.snapshot('phone0')['state'],'paused')
        self.assertIn('offline',monitor.snapshot('phone0')['error'])

    def test_opened_notification_is_removed_immediately(self):
        monitor=self.make_monitor()
        monitor.record('phone0',{'items':[{'id':'a','phone_number':'+123'}]})
        monitor.acknowledge('phone0','a')
        self.assertEqual(monitor.snapshot('phone0')['pending_contacts'],0)

    def test_four_devices_really_overlap_and_no_device_is_scanned_twice(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier=threading.Barrier(4)
        release=threading.Event()
        entered=[]
        guard=threading.Lock()
        def scan(device,base):
            with guard:entered.append(device)
            barrier.wait(timeout=3)
            if not release.wait(3):raise TimeoutError('test scan not released')
            return {'items':[]}
        monitor=self.make_monitor(scan)
        locks={d['udid']:threading.RLock() for d in monitor.devices}
        monitor.lock_for=locks.__getitem__
        # A busy phone must not delay the other devices.
        locks['phone0'].acquire()
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures=[pool.submit(monitor.tick,140) for _ in range(4)]
                try:
                    deadline=__import__('time').monotonic()+3
                    while len(entered)<4 and __import__('time').monotonic()<deadline:
                        release.wait(.01)
                    self.assertEqual(len(set(entered)),4)
                    self.assertNotIn('phone0',entered)
                    self.assertEqual(sum(s['state']=='scanning' for s in monitor.states.values()),4)
                finally:release.set()
                self.assertTrue(all(f.result(timeout=3) for f in futures))
        finally:locks['phone0'].release()


class LeaseTests(unittest.TestCase):
    def test_background_lease_keeps_selected_phone_controllable(self):
        calls=[]
        manager=FocusManager([{'udid':'one'},{'udid':'two'}],'token',lambda d,on:calls.append((d['udid'],on)))
        manager.select('one');calls.clear()
        with manager.notification_lease('two'):
            self.assertEqual(manager.active,'one')
            self.assertEqual(calls,[('two',True)])
        self.assertEqual(calls,[('two',True),('two',False)])

    def test_enable_failure_revokes_target_and_preserves_selection(self):
        manager=FocusManager([{'udid':'one'},{'udid':'two'}],'token',lambda *args:None)
        manager.select('one')
        def transport(device,on):
            if device['udid']=='two' and on:raise OSError('enable failed')
        manager.transport=transport
        with self.assertRaises(OSError):
            with manager.notification_lease('two'):pass
        self.assertEqual(manager.active,'one')

    def test_select_during_scan_does_not_revoke_scanning_phone(self):
        calls=[]
        manager=FocusManager([{'udid':'one'},{'udid':'two'}],'token',lambda d,on:calls.append((d['udid'],on)))
        manager.select('one');calls.clear()
        with manager.notification_lease('one'):
            manager.select('two')
            self.assertEqual(calls,[('two',True)])
        self.assertEqual(calls,[('two',True),('one',False)])

    def test_multiple_background_leases_overlap_without_changing_selection(self):
        manager=FocusManager([{'udid':'one'},{'udid':'two'},{'udid':'three'}],'token',lambda *args:None)
        manager.select('one')
        with manager.notification_lease('two'), manager.notification_lease('three'):
            self.assertEqual(manager.notification_users,{'two':1,'three':1})
            self.assertEqual(manager.active,'one')


if __name__=='__main__':unittest.main()
