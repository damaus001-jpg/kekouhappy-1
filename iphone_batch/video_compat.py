"""Software HEVC decoding for browsers without an HEVC decoder."""
import asyncio
import base64
import io
import contextlib
import json
import socket
import struct
import threading
import time
import urllib.request


class VideoStop(threading.Event):
    """Wake a reader even when a static phone emits no new video packets."""
    def __init__(self):
        super().__init__()
        self.connection = None
        self.connection_lock = threading.Lock()

    def bind(self, connection):
        with self.connection_lock:
            self.connection = connection
            if self.is_set():
                with contextlib.suppress(OSError):
                    connection.shutdown(socket.SHUT_RDWR)

    def set(self):
        super().set()
        with self.connection_lock:
            if self.connection is not None:
                with contextlib.suppress(OSError):
                    self.connection.shutdown(socket.SHUT_RDWR)


def jpeg_frames(port, stopped):
    import av
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f'http://127.0.0.1:{port}'
    with opener.open(base + '/codec', timeout=8) as response:
        description = base64.b64decode(json.load(response)['description'])

    def new_decoder():
        decoder = av.CodecContext.create('hevc', 'r')
        decoder.extradata = description
        decoder.thread_count = 2
        return decoder

    decoder = new_decoder()
    next_image = 0
    got_key = False
    with opener.open(base + '/stream.bin', timeout=8) as stream:
        # The HTTP connection is bounded, but a static display may legitimately
        # stay silent. Stop actively shuts down this local socket on disconnect.
        connection = stream.fp.raw._sock
        connection.settimeout(None)
        stopped.bind(connection)
        while not stopped.is_set():
            header = stream.read(4)
            if len(header) != 4:
                return
            size = struct.unpack('>I', header)[0]
            if not 1 < size <= 8 * 1024 * 1024:
                raise ValueError('Invalid video packet size')
            packet = stream.read(size)
            if len(packet) != size:
                return
            if packet[0] == 2:
                decoder = new_decoder()
            if packet[0] in (0, 2):
                got_key = True
            if not got_key:
                continue
            try:
                frames = decoder.decode(av.Packet(packet[1:]))
            except av.FFmpegError:
                got_key = False
                decoder = new_decoder()
                continue
            for frame in frames:
                now = time.monotonic()
                if now < next_image:
                    continue
                next_image = max(next_image + 1 / 29, now)
                ratio = min(1, 1280 / max(frame.width, frame.height))
                width = max(2, int(frame.width * ratio) // 2 * 2)
                height = max(2, int(frame.height * ratio) // 2 * 2)
                image = frame.reformat(width=width, height=height, format='rgb24',
                                       interpolation='FAST_BILINEAR').to_image()
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=80)
                yield output.getvalue()


class JpegHub:
    """Decode once per phone; slow clients receive only the newest frame."""
    def __init__(self, port):
        self.port = port
        self.stopped = VideoStop()
        self.changed = asyncio.Condition()
        self.latest = None
        self.sequence = 0
        self.clients = 0
        self.task = asyncio.create_task(self.run())

    async def run(self):
        loop = asyncio.get_running_loop()

        async def publish(jpeg):
            async with self.changed:
                self.latest = jpeg
                self.sequence += 1
                self.changed.notify_all()

        def pump():
            for jpeg in jpeg_frames(self.port, self.stopped):
                if self.stopped.is_set():
                    break
                future = asyncio.run_coroutine_threadsafe(publish(jpeg), loop)
                try:
                    future.result(timeout=6)
                except Exception:
                    future.cancel()
                    raise

        try:
            await asyncio.to_thread(pump)
        except Exception:
            pass
        finally:
            self.stopped.set()
            async with self.changed:
                self.changed.notify_all()

    async def serve(self, writer):
        self.clients += 1
        started = False
        sequence = -1
        try:
            while not self.stopped.is_set():
                async with self.changed:
                    try:
                        await asyncio.wait_for(self.changed.wait_for(
                            lambda: self.sequence != sequence or self.stopped.is_set()), 2)
                    except asyncio.TimeoutError:
                        pass
                    if self.stopped.is_set():
                        break
                    jpeg, sequence = self.latest, self.sequence
                if jpeg is None:
                    continue
                if not started:
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\n'
                                 b'Cache-Control: no-store\r\nConnection: close\r\n\r\n')
                    started = True
                writer.write(struct.pack('>I', len(jpeg)) + jpeg)
                await asyncio.wait_for(writer.drain(), 5)
        except (Exception, asyncio.CancelledError):
            pass
        finally:
            self.clients -= 1
            if not self.clients:
                self.stopped.set()
            if not started and not writer.is_closing():
                writer.write(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                await writer.drain()
            writer.close()


async def serve_jpeg(port, writer, owner=None):
    hub = getattr(owner, '_jpeg_hub', None)
    if hub is None or hub.stopped.is_set():
        hub = JpegHub(port)
        if owner is not None:
            owner._jpeg_hub = hub
    await hub.serve(writer)
