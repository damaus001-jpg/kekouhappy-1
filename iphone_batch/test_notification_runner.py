from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from notification_runner import NotificationRunner
from workspace_service import WorkspaceService


class NotificationRunnerTests(unittest.TestCase):
    def test_off_switch_cancels_running_process_and_blocks_new_work(self):
        runner=NotificationRunner()
        command=[sys.executable,'-c','import time;time.sleep(30)']
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(runner.run,'test',command,encoding='utf-8',
                creationflags=0x08000000 if sys.platform=='win32' else 0)
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                with runner.lock:
                    job=runner.jobs.get('test')
                if job:break
                time.sleep(.01)
            self.assertIsNotNone(job)
            time.sleep(.2)
            started=time.monotonic()
            self.assertEqual(runner.set_enabled(False),1)
            with self.assertRaisesRegex(ValueError,'已关闭'):
                future.result(timeout=5)
            self.assertLess(time.monotonic()-started,3)
            self.assertIsNotNone(job['process'].poll())
        with patch('notification_runner.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError,'已关闭'):runner.run('test',command)
            launch.assert_not_called()

    def test_on_switch_can_run_work_again(self):
        runner=NotificationRunner()
        runner.set_enabled(False)
        runner.set_enabled(True)
        result=runner.run('test',[sys.executable,'-c','print("resumed")'],encoding='utf-8',
            creationflags=0x08000000 if sys.platform=='win32' else 0)
        self.assertEqual(result.stdout.strip(),'resumed')
        self.assertEqual(runner.jobs,{})

    def test_off_switch_only_controls_notification_subprocesses(self):
        with tempfile.TemporaryDirectory() as folder:
            service=WorkspaceService(Path(folder))
            service.notification_runner.set_enabled(False)
            result=subprocess.CompletedProcess([],0,'{"status":"ok"}','')
            with patch('workspace_service.subprocess.run',return_value=result) as native:
                self.assertEqual(service._native('phone','send','http://127.0.0.1:8080')['status'],'ok')
                native.assert_called_once()
            with self.assertRaisesRegex(ValueError,'已关闭'):
                service._native('phone','notifications','http://127.0.0.1:8080')
