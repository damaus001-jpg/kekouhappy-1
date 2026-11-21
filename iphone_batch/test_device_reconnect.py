import threading
import time
import unittest
import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from device_reconnect import DeviceReconnects, repair_phone_trust, _run_device_command

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

    def test_bounded_startup_queue_wait_does_not_expire_reconnect(self):
        waiting=threading.Event();waiting.set()
        checked=threading.Event();finished=[]
        def queued(_):checked.set();return waiting.is_set()
        jobs=DeviceReconnects(lambda _:None,lambda _:True,lambda _:finished.append(1) or True,
            threading.Event(),timeout=.1,queued=queued)
        jobs.begin({'udid':'eleven'});self.assertTrue(checked.wait(1))
        time.sleep(.3)
        self.assertTrue(jobs.pending('eleven'));self.assertEqual(finished,[])
        waiting.clear()
        self.assertEqual(self.wait_done(jobs,'eleven')['reconnect_state'],'ready')

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

    def test_trust_wait_does_not_consume_video_readiness_budget(self):
        finished=[]
        jobs=DeviceReconnects(lambda _:time.sleep(.03),lambda _:True,lambda _:finished.append(1) or True,threading.Event(),timeout=.01)
        jobs.begin({'udid':'eleven'});result=self.wait_done(jobs,'eleven')
        self.assertEqual(result['reconnect_state'],'ready')
        self.assertEqual(finished,[1])

class TrustRunnerTests(unittest.TestCase):
    def process(self, stdout='', code=0):
        process=Mock(pid=1234,returncode=code)
        process.communicate.return_value=(stdout,'cache warning')
        process.poll.return_value=None
        return process

    def test_local_identity_success_is_accepted_and_targets_only_requested_device(self):
        value={'ok':True,'message':'verified','system_record_saved':False}
        process=self.process(json.dumps(value))
        with patch('device_reconnect.subprocess.Popen',return_value=process) as launch:
            self.assertEqual(repair_phone_trust({'udid':'phone-six'}),value)
        command=launch.call_args.args[0]
        self.assertEqual(command[-2:],['--device','phone-six'])
        self.assertEqual(Path(command[1]).name,'device_trust.py')
        self.assertEqual(launch.call_args.kwargs['env']['PYMOBILEDEVICE3_UDID'],'phone-six')

    def test_denial_bad_output_or_failed_exit_never_claims_success(self):
        for stdout,code in [(json.dumps({'ok':False,'error':'user denied'}),0),
                            ('bad output',0),('[]',0),(json.dumps({'ok':True}),1)]:
            with self.subTest(stdout=stdout,code=code),patch('device_reconnect.subprocess.Popen',return_value=self.process(stdout,code)):
                with self.assertRaises(ValueError):repair_phone_trust({'udid':'phone-six'})

    def test_timeout_kills_the_runner_and_python_children(self):
        process=self.process()
        python_child=Mock();python_child.name.return_value='python.exe'
        other_child=Mock();other_child.name.return_value='other.exe'
        parent=Mock();parent.children.return_value=[python_child,other_child]
        with patch('device_reconnect.subprocess.Popen',return_value=process),patch('psutil.Process',return_value=parent):
            with self.assertRaisesRegex(ValueError,'timed out'):
                _run_device_command({'udid':'phone-six'},['runner'],0,'timed out')
        python_child.kill.assert_called_once();other_child.kill.assert_not_called()
        process.kill.assert_called_once();process.communicate.assert_called_once_with(timeout=3)

    def test_shutdown_during_trust_confirmation_stops_the_runner(self):
        stopping=threading.Event()
        process=self.process()
        def communicate(timeout):
            if not stopping.is_set():
                stopping.set()
                raise subprocess.TimeoutExpired('runner',timeout)
            return '',''
        process.communicate.side_effect=communicate
        parent=Mock();parent.children.return_value=[]
        with patch('device_reconnect.subprocess.Popen',return_value=process),patch('psutil.Process',return_value=parent):
            with self.assertRaisesRegex(ValueError,'正在关闭'):
                repair_phone_trust({'udid':'phone-six'},stopping)
        process.kill.assert_called_once()

    def test_shutdown_before_request_does_not_start_another_process(self):
        stopping=threading.Event();stopping.set()
        with patch('device_reconnect.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError,'正在关闭'):
                repair_phone_trust({'udid':'phone-six'},stopping)
        launch.assert_not_called()


class RebuildTrustIntegrationTests(unittest.TestCase):
    def fixture(self):
        tree=ast.parse(Path(__file__).with_name('dashboard.py').read_text(encoding='utf-8-sig'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        rebuild=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='rebuild_device')
        target={'udid':'six'};other={'udid':'nine'}
        device_lock=threading.Lock();phone_lock=threading.Lock();registry_lock=threading.Lock()
        events=[]
        context=dict(require_connection=Mock(),enabled=frozenset(['six','nine']),
            workspace_service=SimpleNamespace(device_lock=lambda _:device_lock,phone_lock=phone_lock),
            registry=SimpleNamespace(lock=registry_lock),devices=[target,other],trust_pending=set(),
            manager=SimpleNamespace(lock=threading.Lock(),active='nine'),
            startup_queue=SimpleNamespace(cancel=Mock()),input_readiness_lock=threading.Lock(),input_readiness={},
            reconnects=SimpleNamespace(stage=Mock()),retry_policy=SimpleNamespace(reset=Mock()),stopping=threading.Event(),
            stop_viewer=Mock(side_effect=lambda _:events.append('stop')),
            reset_phone_session=Mock(side_effect=lambda *a,**k:events.append('reset')),
            launch_viewer=Mock(side_effect=lambda _:events.append('start')))
        def trust(device,stopping):
            self.assertIs(device,target);self.assertTrue(device_lock.locked())
            self.assertTrue(phone_lock.acquire(blocking=False));phone_lock.release()
            self.assertTrue(registry_lock.acquire(blocking=False));registry_lock.release()
            events.append('trust')
        context['repair_phone_trust']=Mock(side_effect=trust)
        exec(compile(ast.Module(body=[rebuild],type_ignores=[]),'rebuild_trust','exec'),context)
        return context,target,events,device_lock

    def test_explicit_reconnect_repairs_target_before_restarting_and_leaves_other_phone_free(self):
        state,target,events,lock=self.fixture()
        state['rebuild_device'](target)
        self.assertEqual(events,['stop','trust','reset','start'])
        self.assertEqual(state['manager'].active,'nine')
        self.assertEqual([call.args for call in state['reconnects'].stage.call_args_list],
                         [('six','trusting'),('six','resetting'),('six','starting')])
        self.assertFalse(lock.locked())

    def test_rejected_trust_stays_visible_and_never_starts_viewer(self):
        state,target,events,lock=self.fixture()
        state['repair_phone_trust'].side_effect=ValueError('手机已拒绝信任')
        with self.assertRaisesRegex(ValueError,'拒绝信任'):state['rebuild_device'](target)
        self.assertEqual(target['error'],'手机已拒绝信任')
        self.assertEqual(events,['stop']);self.assertFalse(lock.locked())
        state['reset_phone_session'].assert_not_called();state['launch_viewer'].assert_not_called()

    def test_shutdown_after_trust_never_restarts_video(self):
        state,target,events,lock=self.fixture()
        state['repair_phone_trust'].side_effect=lambda *a,**k:state['stopping'].set()
        with self.assertRaisesRegex(ValueError,'正在关闭'):state['rebuild_device'](target)
        state['reset_phone_session'].assert_not_called();state['launch_viewer'].assert_not_called()
        self.assertFalse(lock.locked())

    def test_reboot_replaces_trust_and_session_reset_and_only_targets_one_phone(self):
        state,target,events,lock=self.fixture()
        state['require_control']=Mock()
        def reboot(device,stopping,stage):
            self.assertIs(device,target);self.assertTrue(lock.locked())
            self.assertFalse(state['workspace_service'].phone_lock.locked())
            events.append('reboot');stage('waiting_boot')
        state['reboot_phone']=Mock(side_effect=reboot)
        state['rebuild_device'](target,reboot=True)
        self.assertEqual(events,['stop','reboot','start'])
        state['repair_phone_trust'].assert_not_called()
        state['reset_phone_session'].assert_not_called()
        self.assertEqual(state['manager'].active,'nine')
        self.assertFalse(lock.locked())


if __name__=='__main__':unittest.main()
