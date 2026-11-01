import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
import viewer_patch
from pymobiledevice3.remote.core_device import screen_stream

viewer_patch.install()

class ClipboardHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.instance = object.__new__(screen_stream.ScreenStreamServer)
        self.instance._password = None
        self.server = await asyncio.start_server(self.instance._handle_http, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.instance._http_port = self.port
        self.clipboard = None
        def native(text=None, *, write=False):
            if write:
                self.clipboard = text
            return self.clipboard
        self.mock = patch('viewer_patch.windows_clipboard', side_effect=native)
        self.mock.start()

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()
        self.mock.stop()

    async def request(self, method='GET', body=None, origin=None, path='/host-clipboard', length=None, token=None):
        payload = b'' if body is None else json.dumps(body).encode()
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        headers = (f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n'
                   f'Content-Type: application/json\r\nContent-Length: {len(payload) if length is None else length}\r\n')
        if token: headers += f'X-Control-Token: {token}\r\n'
        if origin: headers += f'Origin: {origin}\r\n'
        writer.write(headers.encode()+b'\r\n'+payload)
        await writer.drain()
        response = await asyncio.wait_for(reader.read(), 3)
        writer.close()
        await writer.wait_closed()
        head, data = response.split(b'\r\n\r\n',1)
        return int(head.split()[1]), data

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

    async def test_manual_input_rejects_read_only_and_cross_origin(self):
        self.instance._batch_token = 'test-token'
        self.instance._batch_active = False
        self.instance._ensure_hid = AsyncMock()
        for path, body in [('/manual-touch',{'type':'contact','x':1,'y':2}),('/manual-home',{})]:
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

if __name__ == '__main__':
    unittest.main()
