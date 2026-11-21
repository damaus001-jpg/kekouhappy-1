"""Host control grants and process boundaries; no USB or live service actions."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import backend_control
import host_access as access
import host_control as control

KEY = bytes.fromhex('01' * 32)


class HostControlTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / '中文 安装目录'
        self.root.mkdir()
        self.key = patch.object(access, 'load_key', return_value=KEY)
        self.key.start(); self.addCleanup(self.key.stop)

    def install(self):
        (self.root / access.POLICY).write_text('{"protocol":1,"mode":"pikachu-only"}')
        for name in ('runtime/python.exe', 'runtime/node.exe', 'iphone_batch/host_control.py',
                     'iphone_batch/dashboard.py', 'iphone_batch/tunneld_entry.py'):
            file = self.root / name; file.parent.mkdir(parents=True, exist_ok=True); file.touch()
        (self.root / 'VERSION').write_text('0.1.18')

    def proof(self, action='status', **kwargs):
        return access.make_proof(action, self.root, **kwargs)

    def test_signature_is_bound_to_action_directory_key_and_clock(self):
        proof = self.proof()
        cases = [('start', self.root, KEY, time.time()),
                 ('status', self.root.parent, KEY, time.time()),
                 ('status', self.root, b'x' * 32, time.time()),
                 ('status', self.root, KEY, time.time() + 31)]
        for action, root, key, now in cases:
            with self.subTest(action=action, root=root, key=key, now=now):
                with self.assertRaises(access.AuthorizationError):
                    access.verify_proof(action, proof, root, key=key, now=now)

    def test_atomic_replay_rejected_across_callers(self):
        proof = self.proof()
        def attempt(_):
            try:
                access.verify_proof('status', proof, self.root); return True
            except access.AuthorizationError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_invalid_stdin_and_grant_types_rejected(self):
        for raw in ('', 'x', 'x' * 4097):
            with self.assertRaises(access.AuthorizationError):access.read_proof(io.StringIO(raw))
        proof = self.proof(); proof['v'] = True
        with self.assertRaises(access.AuthorizationError):access.verify_proof('status', proof, self.root)

    def test_policy_is_fail_closed_and_development_remains_available(self):
        self.assertFalse(access.host_only(self.root))
        access.require_backend_action('start', self.root)
        (self.root / access.POLICY).write_text('broken')
        with self.assertRaises(access.InstallationError):access.host_only(self.root)

    def test_direct_backend_start_and_stop_rejected_before_process_scan(self):
        self.install()
        backend = backend_control.Backend(); backend.processes = Mock()
        with patch.object(backend_control, 'PROJECT', self.root):
            for action in ('start', 'stop'):
                with self.assertRaises(access.AuthorizationError):getattr(backend, action)()
        backend.processes.assert_not_called()

    def test_dashboard_requires_separate_serve_grant(self):
        self.install()
        with patch.object(access.sys, 'stdin', io.StringIO(json.dumps(self.proof('start')))):
            with self.assertRaises(access.AuthorizationError):access.require_dashboard_launch(self.root)
        with patch.object(access.sys, 'stdin', io.StringIO(json.dumps(self.proof('serve')))):
            access.require_dashboard_launch(self.root)

    def test_install_missing_uses_one_message(self):
        for action in ('status', 'start', 'stop'):
            result, code = control.execute(action, self.proof(action), root=self.root)
            self.assertEqual((code, result['message']), (2, '安装文件缺失'))

    def test_unsigned_calls_do_not_construct_backend(self):
        self.install(); factory = Mock()
        for action in ('status', 'start', 'stop'):
            result, code = control.execute(action, None, root=self.root, backend_factory=factory)
            self.assertEqual((code, result['code']), (3, 'AUTH_REQUIRED'))
        factory.assert_not_called()

    def test_status_and_real_result_states(self):
        self.install(); backend = Mock()
        for rows, state in (([], 'stopped'), ([(Mock(), 'dashboard.py')], 'running'),
                            ([(Mock(), 'controller.py')], 'residual')):
            backend.processes.return_value = rows
            result, code = control.execute('status', self.proof(), root=self.root, backend_factory=lambda: backend)
            self.assertEqual((code, result['state']), (0, state))
        backend.start.assert_not_called(); backend.stop.assert_not_called()

    def test_action_context_and_no_false_success_on_start_stop(self):
        self.install(); backend = Mock()
        def starting():
            access.require_backend_action('start', self.root)
            with self.assertRaises(access.AuthorizationError):access.require_backend_action('stop', self.root)
            return '启动'
        backend.start.side_effect = starting
        backend.processes.return_value = []
        result, code = control.execute('start', self.proof('start'), root=self.root, backend_factory=lambda: backend)
        self.assertEqual((code, result['ok']), (1, False))
        backend.processes.return_value = [(Mock(), 'controller.py')]
        result, code = control.execute('stop', self.proof('stop'), root=self.root, backend_factory=lambda: backend)
        self.assertEqual((code, result['ok']), (1, False))
        with self.assertRaises(access.AuthorizationError):access.require_backend_action('start', self.root)

    def test_concurrent_operation_is_busy_and_can_retry(self):
        self.install(); backend = Mock(); backend.processes.return_value = []
        with control.operation_lock(self.root):
            result, code = control.execute('status', self.proof(), root=self.root, backend_factory=lambda: backend)
        self.assertEqual((code, result['code']), (4, 'BUSY'))
        result, code = control.execute('status', self.proof(), root=self.root, backend_factory=lambda: backend)
        self.assertEqual(code, 0)

    def test_real_start_passes_serve_grant_and_stop_cleans_children(self):
        self.install()
        scripts=self.root/'iphone_batch'
        for name in ('host_access.py','workspace_access.py'):
            shutil.copy2(Path(access.__file__).parent/name,scripts/name)
        (scripts/'controller.py').write_text('import time; time.sleep(90)',encoding='utf-8')
        (scripts/'dashboard.py').write_text(
            "from pathlib import Path\nfrom host_access import require_dashboard_launch\n"
            "require_dashboard_launch(Path(__file__).resolve().parents[1])\n"
            "import subprocess,sys,time\n"
            "child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('controller.py'))],creationflags=0x08000000)\n"
            "Path(__file__).with_name('ready').write_text(str(child.pid))\ntime.sleep(90)\n",encoding='utf-8')
        local=self.root/'isolated-local';keyfile=local/'PikachuSmsBridge/workspace-access.key'
        keyfile.parent.mkdir(parents=True);keyfile.write_text(KEY.hex())
        backend=backend_control.Backend()
        with patch.object(backend_control,'PROJECT',self.root),patch.object(backend_control,'SCRIPTS',scripts), \
                patch.object(backend_control,'LOGS',self.root/'logs'),patch.dict(os.environ,LOCALAPPDATA=str(local)), \
                patch.object(backend,'_ensure_tunneld'),patch.object(backend,'_stop_tunneld'):
            try:
                with access.authorized_operation('start',self.proof('start'),self.root):backend.start()
                self.assertTrue((scripts/'ready').is_file())
                import psutil
                child=psutil.Process(int((scripts/'ready').read_text()))
                with access.authorized_operation('stop',self.proof('stop'),self.root):backend.stop()
                self.assertIsNotNone(backend.started.poll())
                self.assertFalse(child.is_running())
                self.assertEqual(backend.processes(),[])
            finally:
                with access.authorized_operation('stop',self.proof('stop'),self.root):backend.stop()


if __name__ == '__main__':
    unittest.main()
