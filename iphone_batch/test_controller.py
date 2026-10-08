import asyncio
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import controller


class ValidationTests(unittest.TestCase):
    def test_gestures_share_one_session(self):
        compiled = controller.compile_steps([
            {'op': 'tap', 'x': 0, 'y': 65535},
            {'op': 'sleep', 'seconds': 0.5},
            {'op': 'drag', 'x1': 100, 'y1': 100, 'x2': 200, 'y2': 200},
        ])
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0][1], 'tap 0 65535\nsleep 0.5\ndrag 100 100 200 200 30 0.6\n')

    def test_invalid_input_fails_before_execution(self):
        for bad in [-1, 65536, True, 0.5, None]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                controller.compile_steps([{'op': 'tap', 'x': bad, 'y': 0}])
        for bad in [float('nan'), float('inf'), -1, 0]:
            with self.subTest(value=bad), self.assertRaises(ValueError):
                controller.compile_steps([{'op': 'sleep', 'seconds': bad}])
        with self.assertRaises(ValueError):
            controller.compile_steps([{'op': 'tap', 'x': 0, 'y': 0}, {'op': 'swipe'}])
        with self.assertRaises(ValueError):
            controller.compile_steps([{'op': 'type', 'text': '\u4e2d\u6587'}])

    def test_text_cannot_be_interpreted_as_cli_option(self):
        compiled = controller.compile_steps([{'op': 'type', 'text': '--native $(test)'}])
        argv = controller.command_for('DEVICE', compiled[0][0])
        self.assertEqual(argv[-2:], ['--', '--native $(test)'])
        self.assertEqual(controller.device_environment('DEVICE')['PYMOBILEDEVICE3_UDID'], 'DEVICE')
        self.assertNotIn('--udid', argv)


class DeviceSelectionTests(unittest.TestCase):
    def test_single_usb_auto_selection_and_multi_requires_explicit_target(self):
        with patch.object(controller, 'discover', return_value=[{'udid': 'A'}]):
            self.assertEqual(controller.resolve_devices(None), ['A'])
        with patch.object(controller, 'discover', return_value=[{'udid': 'A'}, {'udid': 'B'}]):
            with self.assertRaises(ValueError):
                controller.resolve_devices(None)
            self.assertEqual(controller.resolve_devices(['B', 'B']), ['B'])
            with self.assertRaises(ValueError):
                controller.resolve_devices(['C'])

    def test_parent_routing_is_not_inherited(self):
        with patch.dict(controller.os.environ, {'PYMOBILEDEVICE3_UDID': 'WRONG',
                        'PYMOBILEDEVICE3_TUNNEL': 'WRONG', 'PYMOBILEDEVICE3_NATIVE': '1',
                        'USBMUXD_SOCKET_ADDRESS': 'remote:1234'}):
            env = controller.device_environment('RIGHT')
        self.assertEqual(env['PYMOBILEDEVICE3_UDID'], 'RIGHT')
        self.assertNotIn('PYMOBILEDEVICE3_TUNNEL', env)
        self.assertNotIn('PYMOBILEDEVICE3_NATIVE', env)
        self.assertNotIn('USBMUXD_SOCKET_ADDRESS', env)

    def test_lock_blocks_second_owner_and_releases(self):
        with controller.device_lock('UNIT-TEST-DEVICE'):
            with self.assertRaises(RuntimeError):
                with controller.device_lock('UNIT-TEST-DEVICE'):
                    self.fail('Second controller acquired device')
        with controller.device_lock('UNIT-TEST-DEVICE'):
            pass

    def test_ten_device_limit(self):
        devices = [{'udid': str(n)} for n in range(11)]
        with patch.object(controller, 'discover', return_value=devices):
            self.assertEqual(len(controller.resolve_devices([str(n) for n in range(10)])), 10)
            with self.assertRaises(ValueError):
                controller.resolve_devices([str(n) for n in range(11)])


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.child = self.root / 'child.py'
        self.child.write_text(
            "import json,sys,time,os\n"
            "from pathlib import Path\n"
            "root=Path(sys.argv[1]); udid=sys.argv[2]; mode=sys.argv[3]\n"
            "(root / (udid+'-started')).write_text('started')\n"
            "if mode=='fail': raise SystemExit(2)\n"
            "if mode=='hang': time.sleep(30)\n"
            "if mode=='parallel':\n"
            " deadline=time.monotonic()+4\n"
            " while not all((root / (d+'-started')).exists() for d in ('A','B')):\n"
            "  if time.monotonic()>deadline: raise SystemExit(3)\n"
            "  time.sleep(.02)\n"
            "print(json.dumps({'input':sys.stdin.read(), 'selected':os.environ.get('PYMOBILEDEVICE3_UDID')}))\n",
            encoding='utf-8',
        )

    async def asyncTearDown(self):
        self.temp.cleanup()

    def command(self, udid, args):
        return [sys.executable, str(self.child), str(self.root), udid, args[0]]

    async def test_real_child_processes_execute_in_parallel(self):
        with patch.object(controller, 'command_for', self.command), contextlib.redirect_stdout(io.StringIO()) as output:
            code = await controller.run_all(['A', 'B'], [(['parallel'], 'tap 1 2\n')], 6, 2)
        self.assertEqual(code, 0)
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(records[-1]['successful'], 2)
        for record in records[:-1]:
            self.assertEqual(json.loads(record['stdout'])['selected'], record['udid'])
        self.assertTrue(all('tap 1 2' in record['stdout'] for record in records[:-1]))

    async def test_disabled_developer_mode_stops_before_media_query(self):
        command = [sys.executable, '-c', 'print("false")']
        with patch.object(controller, 'command_for', return_value=command) as calls, contextlib.redirect_stdout(io.StringIO()) as output:
            result = await controller.run_device('A', [(['mounter', 'query-developer-mode-status'], None), (['media'], None)], 3)
        self.assertFalse(result)
        self.assertEqual(calls.call_count, 1)
        self.assertIn('requires_developer_mode', output.getvalue())

    async def test_failure_stops_following_command(self):
        with patch.object(controller, 'command_for', self.command), contextlib.redirect_stdout(io.StringIO()) as output:
            result = await controller.run_device('A', [(['fail'], None), (['parallel'], None)], 3)
        self.assertFalse(result)
        self.assertEqual(len(output.getvalue().splitlines()), 1)

    async def test_timeout_kills_owned_process(self):
        processes = []
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            return process

        with patch.object(controller, 'command_for', self.command), patch.object(asyncio, 'create_subprocess_exec', capture), contextlib.redirect_stdout(io.StringIO()) as output:
            result = await controller.run_device('A', [(['hang'], None)], 0.2)
        self.assertFalse(result)
        self.assertIsNotNone(processes[0].returncode)
        self.assertIn('timeout', output.getvalue())

    async def test_cancel_kills_owned_process(self):
        processes = []
        original = asyncio.create_subprocess_exec

        async def capture(*args, **kwargs):
            process = await original(*args, **kwargs)
            processes.append(process)
            return process

        with patch.object(controller, 'command_for', self.command), patch.object(asyncio, 'create_subprocess_exec', capture):
            task = asyncio.create_task(controller.run_device('A', [(['hang'], None)], 30))
            while not processes:
                await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertIsNotNone(processes[0].returncode)


if __name__ == '__main__':
    unittest.main()
