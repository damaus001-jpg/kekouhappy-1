import asyncio
import json
from pathlib import Path
import tempfile
import queue
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

import touch_diagnostics as td
from test_viewer_patch import ViewerHTTPFixture


class TraceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trace = td.TouchTrace('test-device-05', 8084, self.root, max_bytes=1800)

    async def asyncTearDown(self):
        await self.trace.close()

    def test_packaged_and_noncheckout_environments_are_disabled(self):
        self.assertFalse(td.enabled(self.root))
        (self.root / '.git').mkdir()
        (self.root / '.venv').mkdir()
        with patch.dict('os.environ', {'IPHONE_BATCH_TOUCH_TRACE': '1'}):
            self.assertTrue(td.enabled(self.root))
            (self.root / '8070-host-policy.json').write_text('{}')
            self.assertFalse(td.enabled(self.root))

    def test_input_metadata_cannot_record_text_keys_or_invalid_coordinates(self):
        self.assertEqual(td.input_metadata('/manual-key', {'usages': [4, 5], 'text': 'secret'}),
                         {'path': '/manual-key', 'keys_count': 2})
        metadata = td.input_metadata('/manual-touch', {'type': 'secret', 'x': 'secret', 'y': 9, 'text': 'secret'})
        self.assertNotIn('secret', json.dumps(metadata))

    async def test_rotation_keeps_bounded_prior_session_files_and_export_is_allowlisted(self):
        for i in range(40):
            self.trace.record('test', index=i)
        self.assertTrue(await self.trace.flush())
        self.assertTrue(self.trace.path.with_suffix('.jsonl.1').is_file())
        self.assertLessEqual(len(list(self.root.glob('test-device-05.jsonl*'))), 3)
        (self.root / 'workspace-access.key').write_text('secret')
        (self.root / 'sms.json').write_text('secret')
        with patch.object(td, 'LOG_ROOT', self.root):
            output = td.export_bundle('test-device-05', self.root / 'evidence.zip', self.trace.status())
        with zipfile.ZipFile(output) as archive:
            self.assertIn('status.json', archive.namelist())
            self.assertTrue(all(name.endswith('.jsonl') or '.jsonl.' in name or name in ('status.json', 'README.txt')
                                for name in archive.namelist()))
            self.assertNotIn(b'secret', b''.join(archive.read(name) for name in archive.namelist()))

    async def test_disk_failure_does_not_block_input_recording(self):
        (self.root / 'not-a-directory').write_text('file')
        broken = td.TouchTrace('broken-device', 8084, self.root / 'not-a-directory')
        try:
            await broken.flush()
            # A dead writer or full queue is reflected in status, never raised to input.
            broken.io_error = 'PermissionError'
            for i in range(2200):
                broken.record('input', index=i)
            self.assertEqual(len(broken.events), 128)
            self.assertEqual(broken.status()['io_error'], 'PermissionError')
        finally:
            await broken.close()

    async def test_owned_collector_closes_stdin_and_exits_on_stop(self):
        done = threading.Event()
        lines = queue.Queue()
        lines.put(b'{"kind":"collector-ready","processes":{"backboardd":75}}\n')
        stdout = SimpleNamespace(readline=lines.get, close=lambda: None)
        def close_stdin():
            lines.put(b'')
            done.set()
        process = SimpleNamespace(pid=123, stdout=stdout,
            stdin=SimpleNamespace(close=close_stdin), wait=lambda timeout=3: done.wait(timeout))
        with patch('touch_diagnostics.subprocess.Popen', return_value=process) as launch, \
                patch('controller.device_environment', return_value={}):
            self.trace.set_active(True)
            for _ in range(20):
                if self.trace.collector_state == 'listening':
                    break
                await asyncio.sleep(.01)
            self.assertEqual(self.trace.collector_state, 'listening')
            self.assertIsInstance(launch.call_args.args[0], list)
            await self.trace.close()
        self.assertTrue(done.is_set())
        self.assertEqual(self.trace.collector_state, 'stopped')

    async def test_cancellation_during_launch_still_reaps_the_new_child(self):
        started, release, ended = threading.Event(), threading.Event(), threading.Event()
        process = SimpleNamespace(pid=123, stdout=SimpleNamespace(close=lambda: None),
            stdin=SimpleNamespace(close=ended.set), wait=lambda timeout=3: ended.wait(timeout))
        def launch(*args, **kwargs):
            started.set()
            release.wait(1)
            return process
        with patch('touch_diagnostics.subprocess.Popen', side_effect=launch), \
                patch('controller.device_environment', return_value={}):
            self.trace.set_active(True)
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            self.trace.set_active(False)
            release.set()
            await self.trace.close()
        self.assertTrue(ended.is_set())


class DiagnosticHTTPTests(ViewerHTTPFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.temp = tempfile.TemporaryDirectory()
        self.trace = td.TouchTrace('http-device-05', self.port, Path(self.temp.name))
        self.instance._batch_touch_trace = self.trace

    async def asyncTearDown(self):
        await self.trace.close()
        self.temp.cleanup()
        await super().asyncTearDown()

    async def test_diagnostics_are_signed_and_marking_never_calls_phone(self):
        self.instance._ensure_hid = AsyncMock()
        code, _ = await self.request(path='/touch-diagnostics', authorized=False)
        self.assertEqual(code, 403)
        code, _ = await self.request('POST', {'action': 'mark', 'label': 'left-click-dead'}, path='/touch-diagnostics')
        self.assertEqual(code, 200)
        self.assertEqual(self.trace.events[-1]['kind'], 'incident-marker')
        self.instance._ensure_hid.assert_not_awaited()

    async def test_browser_telemetry_filters_text_and_is_bounded(self):
        code, _ = await self.request('POST', {'action': 'browser', 'events': [
            {'event': 'pointer-down', 'button': 0, 'at': 1234, 'monotonic': 200, 'text': 'secret', 'token': 'secret'}]}, path='/touch-diagnostics')
        self.assertEqual(code, 200)
        self.assertNotIn('secret', json.dumps(list(self.trace.events)))
        self.assertIsInstance(self.trace.events[-1]['at'], str)
        self.assertEqual(self.trace.events[-1]['client_at_ms'], 1234)
        code, _ = await self.request('POST', {'action': 'browser', 'events': [{}] * 49}, path='/touch-diagnostics')
        self.assertEqual(code, 400)

    async def test_touch_request_response_share_id_and_ack_is_explicit(self):
        self.instance._ensure_hid = AsyncMock()
        self.instance._uhs = SimpleNamespace(send_touchscreen=AsyncMock())
        code, _ = await self.request('POST', {'type': 'contact', 'x': 1000, 'y': 2000}, path='/manual-touch')
        self.assertEqual(code, 200)
        events = list(self.trace.events)
        request = next(e for e in events if e['kind'] == 'http-request')
        response = next(e for e in events if e['kind'] == 'http-response')
        self.assertEqual(request['request_id'], response['request_id'])
        self.assertEqual(next(e for e in events if e['kind'] == 'hid-return')['meaning'], 'transport-ack-only')


if __name__ == '__main__':
    unittest.main()
