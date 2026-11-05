import threading
import time
import unittest
from device_reconnect import DeviceReconnects

class ReconnectTests(unittest.TestCase):
    def wait_done(self,jobs,udid):
        deadline=time.monotonic()+2
        while jobs.pending(udid) and time.monotonic()<deadline:time.sleep(.01)
        self.assertFalse(jobs.pending(udid))
        return jobs.snapshot(udid)

    def test_duplicate_click_shares_job_and_only_rebuilds_target(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def rebuild(device):calls.append(device['udid']);entered.set();release.wait(1)
        jobs=DeviceReconnects(rebuild,lambda _:True,lambda _:True,threading.Event())
        device={'udid':'eleven','port':8090,'number':'11'}
        first=jobs.begin(device);self.assertTrue(entered.wait(1))
        self.assertEqual(jobs.begin(device),first)
        self.assertEqual(calls,['eleven'])
        release.set();result=self.wait_done(jobs,'eleven')
        self.assertEqual(result['reconnect_state'],'ready')
        self.assertEqual(result['reconnect_id'],first)
        self.assertEqual(device['port'],8090)

    def test_no_control_restore_before_viewer_ready(self):
        ready=threading.Event();finished=[]
        jobs=DeviceReconnects(lambda _:None,lambda _:ready.is_set(),lambda d:finished.append(d['udid']) or True,threading.Event())
        jobs.begin({'udid':'eleven'});time.sleep(.03)
        self.assertEqual(finished,[])
        ready.set();self.wait_done(jobs,'eleven')
        self.assertEqual(finished,['eleven'])

    def test_failure_is_visible_and_can_retry_with_new_job(self):
        calls=[]
        def rebuild(_):calls.append(1);raise ValueError('手机已断开')
        jobs=DeviceReconnects(rebuild,lambda _:True,lambda _:True,threading.Event())
        first=jobs.begin({'udid':'eleven'});result=self.wait_done(jobs,'eleven')
        self.assertEqual(result['reconnect_error'],'手机已断开')
        self.assertNotEqual(jobs.begin({'udid':'eleven'}),first)
        self.wait_done(jobs,'eleven');self.assertEqual(len(calls),2)

    def test_timeout_exits_and_reports_failure(self):
        jobs=DeviceReconnects(lambda _:None,lambda _:False,lambda _:True,threading.Event(),timeout=.02)
        jobs.begin({'udid':'eleven'})
        self.assertIn('超时',self.wait_done(jobs,'eleven')['reconnect_error'])

    def test_reconnecting_one_device_does_not_mark_other_devices_busy(self):
        release=threading.Event()
        jobs=DeviceReconnects(lambda _:release.wait(1),lambda _:True,lambda _:True,threading.Event())
        jobs.begin({'udid':'eleven'})
        self.assertTrue(jobs.pending('eleven'));self.assertFalse(jobs.pending('five'))
        release.set();self.wait_done(jobs,'eleven')

    def test_stage_and_elapsed_survive_completion(self):
        entered=threading.Event();release=threading.Event()
        def rebuild(device):
            jobs.stage(device['udid'],'resetting');entered.set();release.wait(1)
        jobs=DeviceReconnects(rebuild,lambda _:True,lambda _:True,threading.Event())
        jobs.begin({'udid':'eleven'});self.assertTrue(entered.wait(1))
        self.assertEqual(jobs.snapshot('eleven')['reconnect_stage'],'resetting')
        self.assertGreaterEqual(jobs.snapshot('eleven')['reconnect_elapsed'],0)
        release.set();result=self.wait_done(jobs,'eleven')
        self.assertEqual(result['reconnect_stage'],'ready')
        self.assertGreaterEqual(result['reconnect_elapsed'],0)

    def test_rebuild_time_is_included_in_overall_deadline(self):
        finished=[]
        jobs=DeviceReconnects(lambda _:time.sleep(.03),lambda _:True,lambda _:finished.append(1) or True,threading.Event(),timeout=.01)
        jobs.begin({'udid':'eleven'});result=self.wait_done(jobs,'eleven')
        self.assertEqual(result['reconnect_state'],'failed')
        self.assertEqual(finished,[])

if __name__=='__main__':unittest.main()
