"""Exercise actual access transitions with mocked phone/process boundaries."""
import ast
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from device_policy import connection_allowed, require_connection, save_access, load_enabled, load_readonly


class DeviceAccessTests(unittest.TestCase):
    def fixture(self, directory):
        tree=ast.parse(Path(__file__).with_name('dashboard.py').read_text(encoding='utf-8-sig'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        nodes=[n for n in main.body if isinstance(n,ast.FunctionDef) and n.name in
               ('control_allowed','require_control','change_device_access')]
        factory=ast.parse('def factory(enabled, readonly):\n pass').body[0]
        factory.body=nodes+[ast.parse('return change_device_access, control_allowed').body[0]]
        one,two,off=[{'udid':x,'port':8080+i} for i,x in enumerate(('one','two','off'))]
        phone_lock,device_lock=threading.Lock(),threading.Lock()
        manager=SimpleNamespace(lock=threading.Lock(),active='one',selected='one',transport=Mock(),select=Mock())
        path=Path(directory)/'policy.json'
        path.write_text('{"enabled_udids":["one","two"],"transport":"userspace"}', encoding='utf-8')
        namespace=dict(connection_allowed=connection_allowed,require_connection=require_connection,
            registry=SimpleNamespace(lock=threading.RLock(),known={'one':one,'two':two,'off':off}),
            devices=[one,two,off],reconnects=SimpleNamespace(pending=lambda _:False),trust_pending=set(),
            workspace_service=SimpleNamespace(phone_lock=phone_lock,device_lock=lambda _:device_lock),
            policy_path=path,save_access=save_access,generations={},input_readiness_lock=threading.Lock(),
            input_readiness={},manager=manager,children={'one':SimpleNamespace(poll=lambda:None),
            'two':SimpleNamespace(poll=lambda:None)},stop_viewer=Mock(),launch_viewer=Mock(),
            retry_policy=SimpleNamespace(reset=Mock()))
        namespace['startup_queue']=SimpleNamespace(cancel=Mock())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[factory],type_ignores=[])), 'access_transition','exec'),namespace)
        change,allowed=namespace['factory'](frozenset(['one','two']),frozenset())
        return namespace,change,allowed

    def test_connect_one_does_not_enable_or_restart_others(self):
        with tempfile.TemporaryDirectory() as directory:
            state,change,_=self.fixture(directory)
            target=state['devices'][2]
            result=change(target,{'enabled':True})
            self.assertTrue(result['enabled'])
            state['launch_viewer'].assert_called_once_with(target)
            state['stop_viewer'].assert_not_called()
            self.assertEqual(load_enabled(state['policy_path']),frozenset(['one','two','off']))

    def test_disconnect_revokes_control_stops_only_target_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            state,change,allowed=self.fixture(directory)
            target=state['devices'][0]
            result=change(target,{'enabled':False})
            self.assertFalse(result['enabled'])
            self.assertFalse(allowed(target))
            self.assertTrue(allowed(state['devices'][1]))
            state['manager'].transport.assert_called_once_with(target,False)
            self.assertIsNone(state['manager'].active)
            state['stop_viewer'].assert_called_once_with(target)
            state['launch_viewer'].assert_not_called()
            self.assertEqual(load_enabled(state['policy_path']),frozenset(['two']))

    def test_readonly_keeps_video_running_but_revokes_control(self):
        with tempfile.TemporaryDirectory() as directory:
            state,change,allowed=self.fixture(directory)
            target=state['devices'][0]
            result=change(target,{'readonly':True})
            self.assertTrue(result['enabled'])
            self.assertTrue(result['readonly'])
            self.assertFalse(allowed(target))
            state['stop_viewer'].assert_not_called()
            state['launch_viewer'].assert_not_called()
            state['manager'].transport.assert_called_once_with(target,False)
            self.assertEqual(load_readonly(state['policy_path']),frozenset(['one']))

    def test_busy_phone_task_cannot_be_interrupted_or_change_saved_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state,change,_=self.fixture(directory)
            original=state['policy_path'].read_bytes()
            lock=state['workspace_service'].phone_lock
            lock.acquire()
            try:
                with self.assertRaisesRegex(ValueError,'任务正在执行'):
                    change(state['devices'][0],{'enabled':False})
            finally:lock.release()
            self.assertEqual(state['policy_path'].read_bytes(),original)
            state['stop_viewer'].assert_not_called()

    def test_save_failure_cannot_start_or_stop_a_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            state,change,allowed=self.fixture(directory)
            state['save_access']=Mock(side_effect=OSError('disk unavailable'))
            with self.assertRaises(OSError):change(state['devices'][0],{'enabled':False})
            self.assertTrue(allowed(state['devices'][0]))
            state['stop_viewer'].assert_not_called()
            state['launch_viewer'].assert_not_called()
