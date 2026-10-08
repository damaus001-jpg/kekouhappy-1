import asyncio
import json
import unittest
from unittest.mock import patch
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
