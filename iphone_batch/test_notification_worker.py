from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from notification_runner import NotificationRunner
from notification_worker import serve_banner


class WorkerProtocolTests(unittest.TestCase):
    def test_serial_reads_reuse_imports_but_execute_each_read_independently(self):
        calls = []
        async def execute(args):
            calls.append(args.device)
            return {'source': 'banner', 'items': [], 'call': len(calls)}
        ids = ['a' * 32, 'b' * 32]
        source = io.StringIO(''.join(json.dumps({'request_id': identifier}) + '\n' for identifier in ids))
        output = io.StringIO()
        serve_banner(SimpleNamespace(action='banner', device='one'), execute,
                     input_stream=source, output_stream=output)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r['request_id'] for r in replies], ids)
        self.assertEqual([r['result']['call'] for r in replies], [1, 2])
        self.assertEqual(calls, ['one', 'one'])

    def test_worker_rejects_actions_and_request_payloads_that_could_generate_input(self):
        async def forbidden(_):
            raise AssertionError('must not execute')
        for action in ('send', 'campaign_send', 'open', 'history'):
            with self.assertRaises(ValueError):
                serve_banner(SimpleNamespace(action=action), forbidden)
        source = io.StringIO(json.dumps({'request_id': 'a' * 32, 'action': 'send', 'text': 'Hi'}) + '\n')
        output = io.StringIO()
        serve_banner(SimpleNamespace(action='banner'), forbidden, input_stream=source, output_stream=output)
        self.assertEqual(output.getvalue(), '')

    def test_only_exact_banner_command_uses_persistence(self):
        path = str(Path(__file__).with_name('native_workspace.py').resolve())
        command = [sys.executable, path, '--device', 'one', '--action', 'banner', '--base', 'local']
        self.assertTrue(NotificationRunner.banner_command('one', command))
        self.assertFalse(NotificationRunner.banner_command('two', command))
        self.assertFalse(NotificationRunner.banner_command('one', command + ['--banner-worker']))
        self.assertFalse(NotificationRunner.banner_command('one', [*command[:5], 'send']))


FAKE_WORKER = '''
import asyncio
import argparse
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, ROOT)
from notification_worker import serve_banner
parser = argparse.ArgumentParser()
parser.add_argument('--delay', type=float, default=0)
parser.add_argument('--idle', type=float, default=30)
parser.add_argument('--started')
args, _ = parser.parse_known_args()
calls = 0
async def execute(_):
    global calls
    calls += 1
    if args.started:
        with open(args.started, 'a') as output:
            output.write('request\\n')
    await asyncio.sleep(args.delay)
    return {'pid': os.getpid(), 'call': calls, 'source': 'banner', 'items': []}
serve_banner(SimpleNamespace(action='banner'), execute, idle_seconds=args.idle)
'''


class OwnedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'fake_banner_worker.py'
        self.path.write_text('ROOT = ' + repr(str(Path(__file__).resolve().parent)) + '\n' + FAKE_WORKER)
        self.runner = NotificationRunner()
        self.addCleanup(lambda: self.runner.set_enabled(False))
        self.flags = {'encoding': 'utf-8', 'creationflags': 0x08000000 if os.name == 'nt' else 0}

    def command(self, *args):
        return [sys.executable, str(self.path), *args]

    def read(self, device, command=None, timeout=5):
        with patch.object(self.runner, 'banner_command', return_value=True):
            result = self.runner.run(device, command or self.command(), timeout=timeout, **self.flags)
        self.assertEqual(result.returncode, 0)
        return json.loads(result.stdout)

    def test_repeated_reads_keep_same_process_and_devices_are_isolated(self):
        first = self.read('one')
        again = self.read('one')
        other = self.read('two')
        self.assertEqual(first['pid'], again['pid'])
        self.assertNotEqual(first['pid'], other['pid'])
        self.assertEqual(again['call'], 2)
        self.assertEqual(self.runner.worker_starts, 2)
        self.assertEqual(self.runner.worker_reuses, 1)
        workers = list(self.runner.workers.values())
        self.runner.set_enabled(False)
        self.assertEqual(self.runner.workers, {})
        self.assertTrue(all(w.process.poll() is not None for w in workers))
        self.assertTrue(all(not r.is_alive() for w in workers for r in w.readers))

    def test_timed_out_read_is_not_replayed_and_worker_is_discarded(self):
        marker = str(Path(self.temp.name) / 'requested.txt')
        with patch.object(self.runner, 'banner_command', return_value=True):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.runner.run('one', self.command('--delay', '3', '--started', marker), timeout=.5, **self.flags)
        self.assertEqual(self.runner.workers, {})
        self.assertLessEqual(len(Path(marker).read_text().splitlines()) if Path(marker).exists() else 0, 1)
        result = self.read('one')
        self.assertEqual(result['call'], 1)
        self.assertEqual(self.runner.worker_starts, 2)

    def test_retire_cancels_a_read_without_touching_another_device(self):
        other = self.read('two')
        marker = Path(self.temp.name) / 'started.txt'
        with ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(self.runner, 'banner_command', return_value=True):
                future = pool.submit(self.runner.run, 'one', self.command('--delay', '30', '--started', str(marker)),
                                     timeout=10, **self.flags)
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(marker.exists())
                self.runner.retire('one')
                with self.assertRaisesRegex(ValueError, '已关闭'):
                    future.result(timeout=3)
        self.assertEqual(self.read('two')['pid'], other['pid'])
        self.assertNotIn('one', self.runner.workers)

    def test_idle_worker_exits_and_next_read_gets_a_fresh_process(self):
        command = self.command('--idle', '.2')
        first = self.read('one', command)
        worker = self.runner.workers['one']
        worker.process.wait(timeout=4)
        self.assertEqual(worker.process.returncode, 0, ''.join(worker.stderr))
        second = self.read('one', command)
        self.assertNotEqual(first['pid'], second['pid'])
        self.assertEqual(second['call'], 1)

    def test_parent_eof_exits_cleanly_without_waiting_for_idle_timeout(self):
        self.read('one')
        worker = self.runner.workers['one']
        worker.process.stdin.close()
        self.assertEqual(worker.process.wait(timeout=3), 0)
        worker.close()
        self.assertTrue(all(not r.is_alive() for r in worker.readers))

    def test_wrong_request_id_discards_worker_and_does_not_replay(self):
        script = Path(self.temp.name) / 'wrong_reply.py'
        script.write_text("import sys,json\nfor line in sys.stdin:\n print(json.dumps({'request_id':'wrong','result':{}}),flush=True)\n")
        with patch.object(self.runner, 'banner_command', return_value=True):
            with self.assertRaisesRegex(ValueError, '不匹配'):
                self.runner.run('one', [sys.executable, str(script)], timeout=3, **self.flags)
        self.assertEqual(self.runner.workers, {})
        self.assertEqual(self.runner.worker_starts, 1)

    def test_native_read_error_discards_cached_process(self):
        script = Path(self.temp.name) / 'failed_reply.py'
        script.write_text("import sys,json\nfor line in sys.stdin:\n r=json.loads(line); print(json.dumps({'request_id':r['request_id'],'result':{'error':'USB lost'}}),flush=True)\n")
        with patch.object(self.runner, 'banner_command', return_value=True):
            result = self.runner.run('one', [sys.executable, str(script)], timeout=3, **self.flags)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.runner.workers, {})
        self.assertEqual(self.read('one')['call'], 1)


if __name__ == '__main__':
    unittest.main()
