import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock, Mock
from types import SimpleNamespace
import viewer_patch
from workspace_access import HEADER, signed_header
from pymobiledevice3.remote.core_device import screen_stream

viewer_patch.install()

class ViewerHTTPFixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.instance = object.__new__(screen_stream.ScreenStreamServer)
        self.instance._http_tasks = set()  # upstream 11.29+ tracks owned handlers
        self.instance._password = None
        self.instance._active_service = object()  # fake media session; phone services are mocked
        self.instance._stream_dirty = False
        self.instance._ensure_keyboard = AsyncMock()
        self.server = await asyncio.start_server(self.instance._handle_http, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.instance._http_port = self.port
        self.clipboard = None
        def native(text=None, *, write=False, include_image=False):
            if write:
                self.clipboard = text
            return {'text': self.clipboard, 'image_png': None} if include_image else self.clipboard
        self.mock = patch('viewer_patch.windows_clipboard', side_effect=native)
        self.mock.start()

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.mock.stop()

    async def request(self, method='GET', body=None, origin=None, path='/host-clipboard', length=None, token=None, authorized=True):
        payload = b'' if body is None else json.dumps(body).encode()
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        headers = (f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n'
                   f'Content-Type: application/json\r\nContent-Length: {len(payload) if length is None else length}\r\n')
        if token: headers += f'X-Control-Token: {token}\r\n'
        if authorized: headers += f'{HEADER}: {signed_header(method, f"http://127.0.0.1:{self.port}{path}")}\r\n'
        if origin: headers += f'Origin: {origin}\r\n'
        writer.write(headers.encode()+b'\r\n'+payload)
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 3)
        writer.close()
        await writer.wait_closed()
        head, data = response.split(b'\r\n\r\n',1)
        return int(head.split()[1]), data


class ClipboardHTTPTests(ViewerHTTPFixture):
    async def test_browser_video_report_is_signed_bounded_and_not_input_authorization(self):
        report={'client':'browser1','mode':'hevc','state':'streaming','selected':True,
                'receive_age_ms':12,'decode_age_ms':5000,'queue':0}
        with patch('viewer_patch.wake_media',new_callable=AsyncMock) as wake:
            code,_=await self.request('POST',report,path='/video-health',authorized=False)
            self.assertEqual(code,403)
            with patch('viewer_patch.policy_allows_input',return_value=False):
                code,_=await self.request('POST',report,path='/video-health')
            self.assertEqual(code,200)
            code,data=await self.request(path='/video-health')
            self.assertEqual(json.loads(data)['browser'][0]['decode_age_ms'],5000)
            code,_=await self.request('POST',{'client':'bad','body':'rejected'},path='/video-health')
            self.assertEqual(code,400)
            wake.assert_not_awaited()

    async def test_live_readonly_policy_blocks_input_even_with_stale_owner_flag(self):
        self.instance._batch_token='manager'
        self.instance._batch_active=True
        with patch('viewer_patch.policy_allows_input',return_value=False), patch('viewer_patch.wake_media',new_callable=AsyncMock) as wake:
            for path in ('/manual-touch','/input-health','/input-readiness'):
                code,_=await self.request('POST',{},path=path,token='manager')
                self.assertEqual(code,403,path)
            code,_=await self.request('POST',{'active':True},path='/control-mode',token='manager')
            self.assertEqual(code,403)
            wake.assert_not_awaited()

    async def test_signed_background_video_recovery_does_not_require_input_ownership(self):
        self.instance._batch_token = 'manager'
        self.instance._batch_active = False
        self.instance._rtcp_dest = ('::1', 1234)
        self.instance._subscribers = {object(): object()}
        self.instance._request_recovery_idr = Mock()
        with patch('viewer_patch.wake_media', new_callable=AsyncMock) as wake:
            code, _ = await self.request('POST', {}, path='/pli', authorized=False)
            self.assertEqual(code, 403)
            self.instance._request_recovery_idr.assert_not_called()
            code, _ = await self.request('POST', {}, path='/pli')
            self.assertEqual(code, 202)
            self.instance._request_recovery_idr.assert_called_once_with(reason='browser-pli')
            self.assertFalse(self.instance._batch_active)
            wake.assert_not_awaited()

    async def test_video_health_requires_signature_and_never_wakes_media(self):
        with patch('viewer_patch.wake_media', new_callable=AsyncMock) as wake:
            code, _ = await self.request(path='/video-health', authorized=False)
            self.assertEqual(code, 403)
            code, data = await self.request(path='/video-health')
            self.assertEqual(code, 200)
            self.assertIn('rtp_packets', json.loads(data))
            wake.assert_not_awaited()

    async def test_every_viewer_entry_rejects_unsigned_browser_before_media_wake(self):
        with patch('viewer_patch.wake_media', new_callable=AsyncMock) as wake:
            for path in ['/', '/viewer.js', '/viewer.css', '/codec', '/stream.bin', '/audio.bin', '/jpeg.bin', '/host-clipboard']:
                code, _ = await self.request(path=path, authorized=False)
                self.assertEqual(code, 403, path)
            code, _ = await self.request('POST', {'type':'contact','x':1,'y':1}, path='/manual-touch', authorized=False)
            self.assertEqual(code,403)
            for path in ['/touch','/key','/button','/clipboard','/clipboard/image','/control-mode','/input-readiness']:
                code, _ = await self.request('POST', {}, path=path, authorized=False)
                self.assertEqual(code,403,path)
            wake.assert_not_awaited()

    async def test_signed_background_probe_does_not_grant_input_ownership(self):
        self.instance._batch_token='manager'
        self.instance._batch_active=False
        self.instance._ensure_hid=AsyncMock()
        self.instance._ensure_keyboard=AsyncMock()
        self.instance._kb_service_id=4
        self.instance._uhs=SimpleNamespace(send_keyboard=AsyncMock())
        code, _=await self.request('POST', {}, path='/input-readiness')
        self.assertEqual(code,403)
        code, _=await self.request('POST', {}, path='/input-readiness', token='manager')
        self.assertEqual(code,200)
        self.instance._uhs.send_keyboard.assert_awaited_once_with(4,[])
        code, _=await self.request('POST', {'usages':[4]}, path='/manual-key', token='manager')
        self.assertEqual(code,403)

    async def test_compatible_video_rejects_cross_origin_and_writes(self):
        with patch('video_compat.serve_jpeg') as serve:
            code, _ = await self.request(path='/jpeg.bin', origin='https://example.com')
            self.assertEqual(code, 403)
            code, _ = await self.request('POST', path='/jpeg.bin')
            self.assertEqual(code, 405)
            serve.assert_not_called()

    async def test_manual_drag_finishes_at_mouse_endpoint_before_release(self):
        self.instance._ensure_hid = AsyncMock()
        touch = AsyncMock()
        self.instance._uhs = SimpleNamespace(send_touchscreen=touch)
        code, _ = await self.request('POST', {'type':'release','x':12000,'y':31000,'settle':True}, path='/manual-touch')
        self.assertEqual(code, 200)
        self.assertEqual(touch.await_count, 3)
        calls = touch.await_args_list
        self.assertTrue(all(call.args[1:] == (12000,31000) for call in calls))
        self.assertEqual(calls[0].args[0], calls[1].args[0])
        self.assertNotEqual(calls[1].args[0], calls[2].args[0])
        self.assertIsNone(self.instance._batch_contact)

    async def test_manual_key_waits_for_phone_dispatch_and_never_queues(self):
        self.instance._ensure_hid=AsyncMock()
        self.instance._ensure_keyboard=AsyncMock()
        self.instance._kb_service_id=9
        self.instance._uhs=SimpleNamespace(send_keyboard=AsyncMock())
        self.instance._hid_queue=asyncio.Queue()
        code,_=await self.request('POST',{'usages':[0xE3,0x19]},path='/manual-key')
        self.assertEqual(code,200)
        self.instance._uhs.send_keyboard.assert_awaited_once_with(9,[0xE3,0x19])
        self.assertTrue(self.instance._hid_queue.empty())

    async def test_manual_paste_releases_once_without_return(self):
        self.instance._ensure_hid=AsyncMock()
        self.instance._kb_service_id=9
        keys=AsyncMock()
        self.instance._uhs=SimpleNamespace(send_keyboard=keys)
        code,_=await self.request('POST',{},path='/manual-paste')
        self.assertEqual(code,200)
        self.assertEqual([call.args for call in keys.await_args_list],[(9,[227,25]),(9,[])])

    async def test_manual_paste_failure_still_releases_and_never_retries(self):
        self.instance._ensure_hid=AsyncMock()
        self.instance._stop_hid=AsyncMock()
        self.instance._kb_service_id=9
        keys=AsyncMock(side_effect=[ConnectionError('lost acknowledgement'),None])
        self.instance._uhs=SimpleNamespace(send_keyboard=keys)
        code,_=await self.request('POST',{},path='/manual-paste')
        self.assertEqual(code,500)
        self.assertEqual([call.args for call in keys.await_args_list],[(9,[227,25]),(9,[])])

    async def test_composer_focus_registers_keyboard_before_touch(self):
        self.instance._ensure_hid=AsyncMock()
        events=[]
        async def keyboard():events.append('keyboard')
        async def touch(*args,**kwargs):events.append('touch')
        self.instance._ensure_keyboard=AsyncMock(side_effect=keyboard)
        self.instance._uhs=SimpleNamespace(send_touchscreen=AsyncMock(side_effect=touch))
        with patch('visual_composer.input_point',return_value={'x':.4,'y':.8}):
            code,_=await self.request('POST',{},path='/manual-composer-focus')
        self.assertEqual(code,200)
        self.assertEqual(events,['keyboard','touch','touch'])
        self.assertIsNone(self.instance._batch_contact)

    async def test_manual_key_failure_resets_connection_without_retry(self):
        self.instance._ensure_hid=AsyncMock()
        self.instance._ensure_keyboard=AsyncMock()
        self.instance._stop_hid=AsyncMock()
        self.instance._kb_service_id=9
        self.instance._uhs=SimpleNamespace(send_keyboard=AsyncMock(side_effect=ConnectionAbortedError('dead HID')))
        code,_=await self.request('POST',{'usages':[0xE3,0x19]},path='/manual-key')
        self.assertEqual(code,500)
        self.instance._uhs.send_keyboard.assert_awaited_once()
        self.instance._stop_hid.assert_awaited_once()

    async def test_manual_key_validates_usages_and_control_owner(self):
        self.instance._ensure_hid=AsyncMock()
        for usages in [[True],[-1],[256],'abc',list(range(17))]:
            code,_=await self.request('POST',{'usages':usages},path='/manual-key')
            self.assertEqual(code,400)
        self.instance._batch_token='test';self.instance._batch_active=False
        code,_=await self.request('POST',{'usages':[]},path='/manual-key')
        self.assertEqual(code,403)
        self.instance._ensure_hid.assert_not_awaited()

    async def test_health_is_same_origin_control_only_and_emits_no_pressed_key(self):
        self.instance._ensure_hid = AsyncMock()
        self.instance._ensure_keyboard = AsyncMock()
        self.instance._kb_service_id = 9
        self.instance._uhs = SimpleNamespace(send_keyboard=AsyncMock())
        self.instance._batch_token = 'token'
        self.instance._batch_active = False
        code, _ = await self.request('POST', {}, path='/input-health')
        self.assertEqual(code, 403)
        self.instance._batch_active = True
        code, _ = await self.request('POST', {}, path='/input-health', origin='https://example.com')
        self.assertEqual(code, 403)
        code, _ = await self.request(path='/input-health')
        self.assertEqual(code, 405)
        self.instance._ensure_hid.assert_not_awaited()
        code, data = await self.request('POST', {}, path='/input-health')
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(data)['ok'])
        self.instance._uhs.send_keyboard.assert_awaited_once_with(9, [])

    async def test_input_queued_before_recovery_is_not_executed(self):
        self.instance._ensure_hid = AsyncMock()
        self.instance._batch_input_lock = asyncio.Lock()
        await self.instance._batch_input_lock.acquire()
        request = asyncio.create_task(self.request('POST', {'usages':[40]}, path='/manual-key'))
        for _ in range(10):
            await asyncio.sleep(.005)
        self.instance._batch_input_generation = 1
        self.instance._batch_input_lock.release()
        code, _ = await request
        self.assertEqual(code, 409)
        self.instance._ensure_hid.assert_not_awaited()

    async def test_recovering_rejects_new_input_without_queuing(self):
        self.instance._batch_recovering = True
        self.instance._ensure_hid = AsyncMock()
        code, _ = await self.request('POST', {'usages':[40]}, path='/manual-key')
        self.assertEqual(code, 503)
        self.instance._ensure_hid.assert_not_awaited()

    async def test_timed_out_input_clears_connection_and_is_not_replayed(self):
        self.instance._ensure_hid = AsyncMock(side_effect=asyncio.TimeoutError())
        self.instance._stop_hid = AsyncMock()
        code, _ = await self.request('POST', {'usages':[40]}, path='/manual-key')
        self.assertEqual(code, 503)
        self.instance._stop_hid.assert_awaited_once()
        self.instance._ensure_hid.assert_awaited_once()

    async def test_manual_input_rejects_read_only_and_cross_origin(self):
        self.instance._batch_token = 'test-token'
        self.instance._batch_active = False
        self.instance._ensure_hid = AsyncMock()
        for path, body in [('/manual-touch',{'type':'contact','x':1,'y':2}),('/manual-home',{}),('/manual-paste',{}),('/manual-composer-focus',{})]:
            code, _ = await self.request('POST', body, path=path)
            self.assertEqual(code, 403)
            code, _ = await self.request('POST', body, path=path, origin='https://example.com')
            self.assertEqual(code, 403)
        self.instance._ensure_hid.assert_not_called()

    async def test_manual_home_presses_and_releases_phone_home_button(self):
        self.instance._ensure_hid = AsyncMock()
        button = AsyncMock()
        self.instance._indigo = SimpleNamespace(send_button=button)
        code, _ = await self.request('POST', {}, path='/manual-home')
        self.assertEqual(code, 200)
        self.assertEqual(button.await_count, 2)
        first, last = button.await_args_list
        self.assertEqual(first.args[:2], screen_stream._NAMED_BUTTONS['home'][:2])
        self.assertEqual(first.args[:2], last.args[:2])
        self.assertNotEqual(first.args[2], last.args[2])

    async def test_invalid_manual_coordinates_never_reach_phone(self):
        self.instance._ensure_hid = AsyncMock()
        for x in [-1, 65536, True, '2']:
            code, _ = await self.request('POST', {'type':'contact','x':x,'y':2}, path='/manual-touch')
            self.assertEqual(code, 400)
        self.instance._ensure_hid.assert_not_called()

    async def test_unicode_round_trip(self):
        value = '\u4e2d\u6587\nline two \U0001f600'
        code, data = await self.request('POST', {'text':value})
        self.assertEqual(code, 200)
        code, data = await self.request()
        self.assertEqual(json.loads(data)['text'], value)

    async def test_host_clipboard_returns_native_image_without_browser_permission(self):
        content = {'text': None, 'image_png': 'native-png-data'}
        with patch('viewer_patch.windows_clipboard', return_value=content) as native:
            code, data = await self.request()
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(data), content)
        native.assert_called_once_with(include_image=True)

    async def test_cross_origin_cannot_read_or_write(self):
        for method in ['GET', 'POST']:
            code, _ = await self.request(method, {'text':'untrusted'}, origin='https://example.com')
            self.assertEqual(code, 403)
        self.assertIsNone(self.clipboard)

    async def test_invalid_and_oversized_text_rejected(self):
        for body in [{'text':None}, {'text':'bad\x00text'}, []]:
            code, _ = await self.request('POST', body)
            self.assertEqual(code, 400)
        code, _ = await self.request('POST', {}, length=viewer_patch.MAX_TEXT_BYTES+1)
        self.assertEqual(code, 413)
        self.assertIsNone(self.clipboard)

    async def test_existing_chinese_page_still_served(self):
        code, data = await self.request(path='/')
        self.assertEqual(code,200)
        self.assertIn(b'lang="zh-CN"',data)
        self.assertIn('clipboard-copy'.encode(),data)

    async def test_viewer_script_refreshes_without_restarting_device(self):
        self.instance._audio_default_on = False
        self.instance._compensate = False
        with patch('viewer_patch.viewer_script', return_value=b'const newest = true;') as read:
            code, data = await self.request(path='/viewer.js')
            self.assertEqual(code, 200)
            self.assertIn(b'const newest = true;', data)
            read.assert_called_once()

if __name__ == '__main__':
    unittest.main()
