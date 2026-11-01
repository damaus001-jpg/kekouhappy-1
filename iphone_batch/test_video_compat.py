import asyncio
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from video_compat import serve_jpeg


class SharedVideoTests(unittest.IsolatedAsyncioTestCase):
    async def test_two_clients_share_decoder_and_stop_after_disconnect(self):
        owner = SimpleNamespace()

        def frames(port, stopped):
            while not stopped.is_set():
                yield b'jpeg-frame'
                stopped.wait(.02)

        async def handle(reader, writer):
            await serve_jpeg(8084, writer, owner)

        with patch('video_compat.jpeg_frames', side_effect=frames) as decode:
            server = await asyncio.start_server(handle, '127.0.0.1', 0)
            port = server.sockets[0].getsockname()[1]
            clients = await asyncio.gather(*(asyncio.open_connection('127.0.0.1', port) for _ in range(2)))
            try:
                for reader, writer in clients:
                    header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)
                    self.assertIn(b'200 OK', header)
                    size = struct.unpack('>I', await reader.readexactly(4))[0]
                    self.assertEqual(await reader.readexactly(size), b'jpeg-frame')
                decode.assert_called_once()
            finally:
                for reader, writer in clients:
                    writer.close()
                    await writer.wait_closed()
                server.close()
                await server.wait_closed()
                for _ in range(100):
                    if owner._jpeg_hub.stopped.is_set():
                        break
                    await asyncio.sleep(.02)
                self.assertTrue(owner._jpeg_hub.stopped.is_set())
                await asyncio.wait_for(owner._jpeg_hub.task, 2)

    async def test_decoder_failure_returns_unavailable(self):
        async def handle(reader, writer):
            await serve_jpeg(8084, writer)

        with patch('video_compat.jpeg_frames', side_effect=OSError('device offline')):
            server = await asyncio.start_server(handle, '127.0.0.1', 0)
            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
                response = await asyncio.wait_for(reader.read(), 2)
                self.assertIn(b'503 Service Unavailable', response)
                writer.close()
                await writer.wait_closed()
            finally:
                server.close()
                await server.wait_closed()
