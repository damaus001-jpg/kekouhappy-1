import asyncio
import struct
import io
import sys
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from video_compat import serve_jpeg, jpeg_frames, VideoStop


class DecoderRecoveryTests(unittest.TestCase):
    def test_decode_error_requests_key_and_preserves_reference_boundary(self):
        decoded, requests = [], []
        class DecodeError(Exception): pass
        class Decoder:
            def decode(self, packet):
                decoded.append(packet[0])
                if packet[0] == 1:
                    raise DecodeError()
                return []
        av = SimpleNamespace(CodecContext=SimpleNamespace(create=lambda *args: Decoder()),
                             Packet=lambda data: data, FFmpegError=DecodeError)
        stream = io.BytesIO(b''.join(struct.pack('>I', 2) + bytes([kind, i])
            for i, kind in enumerate([0, 1, 1, 0, 1])))
        stream.fp = SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=lambda _: None)))
        class Opener:
            def open(self, target, timeout):
                if isinstance(target, str) and target.endswith('/codec'):
                    return io.BytesIO(json.dumps({'description': 'AAAA'}).encode())
                if isinstance(target, str):
                    return stream
                requests.append(target.full_url)
                return io.BytesIO()
        stopped = VideoStop()
        with patch.dict(sys.modules, {'av': av}), patch('video_compat.signed_opener', return_value=Opener()):
            self.assertEqual(list(jpeg_frames(12345, stopped)), [])
        self.assertEqual(decoded, [0, 1, 3, 4])
        self.assertEqual(requests, ['http://127.0.0.1:12345/pli'])
        self.assertEqual(stopped.diagnostics['errors'], 1)


class SharedVideoTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_frame_is_not_reencoded_as_periodic_network_traffic(self):
        owner = SimpleNamespace()
        def frames(port, stopped):
            yield b'static'
            stopped.wait(5)
        async def handle(reader, writer):
            await serve_jpeg(8084, writer, owner, reader=reader)
        with patch('video_compat.jpeg_frames', side_effect=frames):
            server = await asyncio.start_server(handle, '127.0.0.1', 0)
            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
            try:
                await reader.readuntil(b'\r\n\r\n')
                size = struct.unpack('>I', await reader.readexactly(4))[0]
                self.assertEqual(await reader.readexactly(size), b'static')
                with self.assertRaises(asyncio.TimeoutError):
                    await asyncio.wait_for(reader.readexactly(4), 2.2)
            finally:
                writer.close()
                await writer.wait_closed()
                server.close()
                await server.wait_closed()
                await asyncio.wait_for(owner._jpeg_hub.task, 1)

    async def test_two_clients_share_decoder_and_stop_after_disconnect(self):
        owner = SimpleNamespace()

        def frames(port, stopped):
            while not stopped.is_set():
                yield b'jpeg-frame'
                stopped.wait(.02)

        async def handle(reader, writer):
            await serve_jpeg(8084, writer, owner, reader=reader)

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

    async def test_static_video_stops_on_last_client_eof_and_can_wake_again(self):
        owner = SimpleNamespace()

        def frames(port, stopped):
            yield b'one-static-frame'
            stopped.wait(5)

        async def handle(reader, writer):
            await serve_jpeg(8084, writer, owner, reader=reader)

        with patch('video_compat.jpeg_frames', side_effect=frames) as decode:
            server = await asyncio.start_server(handle, '127.0.0.1', 0)
            try:
                port = server.sockets[0].getsockname()[1]
                for _ in range(2):
                    reader, writer = await asyncio.open_connection('127.0.0.1', port)
                    try:
                        await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)
                        size = struct.unpack('>I', await reader.readexactly(4))[0]
                        self.assertEqual(await reader.readexactly(size), b'one-static-frame')
                        hub = owner._jpeg_hub
                    finally:
                        writer.close()
                        await writer.wait_closed()
                    await asyncio.wait_for(hub.task, 1)
                    self.assertTrue(hub.stopped.is_set())
                    self.assertEqual(hub.clients, 0)
                self.assertEqual(decode.call_count, 2)
            finally:
                server.close()
                await server.wait_closed()

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
