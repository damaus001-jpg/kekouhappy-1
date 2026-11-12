"""Exercise ownership boundaries and shutdown without touching live phones."""
import unittest
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import psutil

import backend_control as control


class BackendControlTests(unittest.TestCase):
    def process(self, pid, entry='dashboard.py', executable=None):
        process = Mock()
        process.pid = pid
        process.exe.return_value = str(executable or control.PYTHON)
        process.cmdline.return_value = [str(control.PYTHON), str(control.SCRIPTS / entry)]
        process.children.return_value = []
        return process

    def test_only_exact_project_script_and_environment_are_owned(self):
        self.assertEqual(control.process_entry(self.process(1)), 'dashboard.py')
        foreign = self.process(2, executable=control.PROJECT / 'other' / 'python.exe')
        self.assertIsNone(control.process_entry(foreign))
        foreign = self.process(3)
        foreign.cmdline.return_value[1] = str(control.PROJECT / 'other' / 'dashboard.py')
        self.assertIsNone(control.process_entry(foreign))
        module = self.process(4)
        module.cmdline.return_value = [str(control.PYTHON), '-c', str(control.SCRIPTS / 'dashboard.py')]
        self.assertIsNone(control.process_entry(module))

    def test_relative_project_entry_is_recognized(self):
        process = self.process(1)
        process.cmdline.return_value[1] = 'iphone_batch/dashboard.py'
        process.cwd.return_value = str(control.PROJECT)
        self.assertEqual(control.process_entry(process), 'dashboard.py')

    @patch.object(control.subprocess, 'Popen')
    def test_start_does_not_duplicate_existing_dashboard(self, popen):
        backend = control.Backend()
        backend.processes = Mock(return_value=[(self.process(1), 'dashboard.py')])
        self.assertIn('已经运行', backend.start())
        popen.assert_not_called()

    @patch.object(control.subprocess, 'Popen')
    def test_start_rejects_orphaned_viewers(self, popen):
        backend = control.Backend()
        backend.processes = Mock(return_value=[(self.process(2, 'controller.py'), 'controller.py')])
        with self.assertRaisesRegex(RuntimeError, '残留'):
            backend.start()
        popen.assert_not_called()

    @patch.object(control.psutil, 'wait_procs', return_value=([], []))
    def test_stop_includes_descendants_and_orphans(self, wait):
        main, child, orphan = self.process(1), self.process(2), self.process(3)
        main.children.return_value = [child]
        backend = control.Backend()
        backend.processes = Mock(side_effect=[[(main, 'dashboard.py'), (orphan, 'pmd_entry.py')], []])
        self.assertIn('全部关闭', backend.stop())
        for process in (main, child, orphan):
            process.suspend.assert_called()
            process.terminate.assert_called_once()

    def test_failed_collection_resumes_parents_without_terminating(self):
        main = self.process(1)
        main.children.side_effect = psutil.AccessDenied(1)
        backend = control.Backend()
        backend.processes = Mock(return_value=[(main, 'dashboard.py')])
        with self.assertRaises(psutil.AccessDenied):
            backend.stop()
        main.resume.assert_called_once()
        main.terminate.assert_not_called()

    @patch.object(control.psutil, 'wait_procs')
    def test_surviving_processes_are_reported_as_failure(self, wait):
        main = self.process(1)
        wait.return_value = ([], [main])
        backend = control.Backend()
        backend.processes = Mock(return_value=[(main, 'dashboard.py')])
        with self.assertRaisesRegex(RuntimeError, '未退出'):
            backend.stop()
        main.kill.assert_called_once()

    def test_real_isolated_start_and_process_tree_shutdown(self):
        # Fake backend in a temporary checkout: no ports, phone APIs or imports.
        with tempfile.TemporaryDirectory(dir=control.PROJECT) as directory:
            root = Path(directory)
            scripts = root / 'iphone_batch'
            scripts.mkdir()
            (scripts / 'dashboard.py').write_text(
                "import subprocess, sys, time\n"
                "from pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                "Path(__file__).with_name('child.pid').write_text(str(child.pid))\n"
                "time.sleep(120)\n", encoding='utf-8')
            backend = control.Backend()
            child = None
            with patch.object(control, 'PROJECT', root), \
                    patch.object(control, 'SCRIPTS', scripts), \
                    patch.object(control, 'LOGS', root / 'logs'):
                try:
                    self.assertIn('已启动', backend.start())
                    deadline = time.monotonic() + 5
                    while not (scripts / 'child.pid').exists() and time.monotonic() < deadline:
                        time.sleep(.05)
                    child = psutil.Process(int((scripts / 'child.pid').read_text()))
                    self.assertIn('运行中', backend.status())
                    self.assertIn('全部关闭', backend.stop())
                    self.assertFalse(child.is_running())
                    self.assertEqual(backend.processes(), [])
                finally:
                    backend.stop()
                    if child and child.is_running():
                        child.kill()
                        child.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
