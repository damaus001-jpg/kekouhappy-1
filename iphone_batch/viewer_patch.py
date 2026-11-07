"""Local viewer assets and a same-origin, loopback-only Windows clipboard bridge."""
import asyncio
import base64
import io
import json
import os
import hmac
import logging
import time
from pathlib import Path
from workspace_access import AccessVerifier, HEADER
from input_health import check_input, clear_input, record_input, ensure_input_services
from video_idle import ensure_idle_monitor, stream_until_disconnect, touch_media, wake_media

MAX_TEXT_BYTES = 1024 * 1024
MAX_CLIPBOARD_IMAGE_BYTES = 16 * 1024 * 1024


def viewer_script(folder):
    return b'\n'.join((folder / name).read_bytes() for name in ('pointer_input.js', 'input_health.js', 'viewer.js'))


class ReplayReader:
    """Replay inspected HTTP headers before delegating the existing stream reader."""
    def __init__(self, prefix, reader):
        self.prefix = bytearray(prefix)
        self.reader = reader

    async def readline(self):
        if self.prefix:
            end = self.prefix.find(b'\n') + 1
            if not end:
                end = len(self.prefix)
            result = bytes(self.prefix[:end])
            del self.prefix[:end]
            return result
        return await self.reader.readline()

    async def readexactly(self, size):
        count = min(size, len(self.prefix))
        result = bytes(self.prefix[:count])
        del self.prefix[:count]
        if count < size:
            result += await self.reader.readexactly(size - count)
        return result


def windows_clipboard(text=None, *, write=False, include_image=False):
    import win32clipboard as clipboard
    for attempt in range(15):
        try:
            clipboard.OpenClipboard()
            break
        except Exception:
            if attempt == 14:
                raise
            time.sleep(0.02)
    try:
        if write:
            clipboard.EmptyClipboard()
            clipboard.SetClipboardText(text, clipboard.CF_UNICODETEXT)
            return None
        value = (clipboard.GetClipboardData(clipboard.CF_UNICODETEXT)
                 if clipboard.IsClipboardFormatAvailable(clipboard.CF_UNICODETEXT) else None)
        if not include_image:
            return value
        # Read text and image while holding the same clipboard snapshot. A copied
        # browser image may also carry a URL; the paste action prefers its image.
        image_png = None
        formats = (clipboard.RegisterClipboardFormat('PNG'), 17, clipboard.CF_DIB)
        for image_format in formats:  # PNG, CF_DIBV5, CF_DIB
            if not clipboard.IsClipboardFormatAvailable(image_format):
                continue
            from PIL import Image
            raw = clipboard.GetClipboardData(image_format)
            if not isinstance(raw, bytes) or len(raw) > 64 * 1024 * 1024:
                raise ValueError('clipboard image exceeds size limit')
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > 32 * 1024 * 1024:
                    raise ValueError('clipboard image exceeds pixel limit')
                output = io.BytesIO()
                image.save(output, format='PNG')
            png = output.getvalue()
            if len(png) > MAX_CLIPBOARD_IMAGE_BYTES:
                raise ValueError('clipboard image exceeds size limit')
            image_png = base64.b64encode(png).decode('ascii')
            break
        return {'text': value, 'image_png': image_png}
    finally:
        clipboard.CloseClipboard()


async def reply(writer, code, data):
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    reason = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 405: 'Method Not Allowed',
              409: 'Conflict', 413: 'Payload Too Large', 500: 'Internal Server Error', 503: 'Service Unavailable'}[code]
    writer.write((f'HTTP/1.1 {code} {reason}\r\nContent-Type: application/json; charset=utf-8\r\n'
                  f'Cache-Control: no-store\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n').encode() + payload)
    await writer.drain()
    writer.close()


def install():
    from pasteboard_text import install as install_text
    install_text()
    from pymobiledevice3.remote.core_device import screen_stream
    folder = Path(__file__).resolve().parent / 'web'
    screen_stream.VIEWER_HTML = (folder / 'viewer.html').read_bytes()
    screen_stream.VIEWER_JS_TEMPLATE = viewer_script(folder)
    if getattr(screen_stream.ScreenStreamServer, '_batch_patched', False):
        return
    access = AccessVerifier()
    screen_stream.ScreenStreamServer._batch_patched = True
    screen_stream.ScreenStreamServer._ensure_hid = ensure_input_services
    token = os.environ.get('IPHONE_BATCH_CONTROL_TOKEN')
    def token_for(instance):
        return getattr(instance, '_batch_token', token)
    def active(instance):
        return not token_for(instance) or getattr(instance, '_batch_active', False)
    originals = {name: getattr(screen_stream.ScreenStreamServer, name)
                 for name in ('_handle_touch', '_handle_key', '_handle_button')}
    def input_lock(instance):
        if not hasattr(instance, '_batch_input_lock'):
            instance._batch_input_lock = asyncio.Lock()
        return instance._batch_input_lock
    from video_idle import install as install_idle_video
    install_idle_video(screen_stream.ScreenStreamServer, input_lock)
    for name, original_action in originals.items():
        def wrap_action(action, kind):
            async def guarded(instance, body):
                generation = getattr(instance, '_batch_input_generation', 0)
                if getattr(instance, '_batch_recovering', False):
                    return 503, b'input connection recovering'
                if active(instance):
                    await asyncio.wait_for(wake_media(instance), 12)
                async with input_lock(instance):
                    if not active(instance):
                        return 403, b'device is read-only'
                    if generation != getattr(instance, '_batch_input_generation', 0):
                        return 409, b'input connection changed; repeat manually'
                    try:
                        result = await asyncio.wait_for(action(instance, body), 4)
                    except Exception:
                        await clear_input(instance)
                        raise
                    if result[0] == 200:
                        record_input(instance, kind, json.loads(body))
                    return result
            return guarded
        setattr(screen_stream.ScreenStreamServer, name, wrap_action(original_action, name))
    original = screen_stream.ScreenStreamServer._handle_http

    async def dispatch_handle(self, reader, writer):
        first = await reader.readline()
        parts = first.decode('latin-1').strip().split()
        if len(parts) != 3:
            return await reply(writer, 400, {'error': 'invalid request'})
        device_token = token_for(self)
        path = parts[1].partition('?')[0]
        async def delegate(replay):
            serving = original(self, replay, writer)
            if path in ('/stream.bin', '/audio.bin'):
                return await stream_until_disconnect(serving, reader)
            return await serving
        async def prepare_media():
            try:
                await asyncio.wait_for(wake_media(self), 12)
                return True
            except Exception as error:
                logging.getLogger(__name__).warning('Media wake failed: port=%s error=%s', self._http_port, type(error).__name__)
                await reply(writer, 503, {'error': '视频或控制服务正在准备，请稍后重试'})
                return False
        special = path in ('/host-clipboard', '/device-clipboard-info', '/control-mode', '/translation', '/jpeg.bin', '/manual-touch', '/manual-home', '/manual-key', '/manual-paste', '/manual-composer-focus', '/input-health', '/input-readiness')
        restricted = device_token and (parts[0] == 'POST' or path.startswith('/clipboard') or path == '/host-clipboard')
        prefix = bytearray(first)
        headers = {}
        for _ in range(100):
            line = await reader.readline()
            prefix.extend(line)
            if line in (b'\r\n', b'\n', b''):
                break
            if len(line) > 8192:
                return await reply(writer, 400, {'error': 'invalid headers'})
            name, sep, value = line.decode('latin-1').partition(':')
            if not sep:
                return await reply(writer, 400, {'error': 'invalid headers'})
            headers[name.lower()] = value.strip()
        else:
            return await reply(writer, 400, {'error': 'too many headers'})
        peer = writer.get_extra_info('peername')
        host = headers.get('host', '')
        origin = headers.get('origin')
        # No CORS: reject cross-site reads/writes, including HTML form submissions.
        allowed_hosts = {f'127.0.0.1:{self._http_port}', f'localhost:{self._http_port}', f'[::1]:{self._http_port}'}
        if (not peer or peer[0] not in ('127.0.0.1', '::1') or host not in allowed_hosts
                or headers.get('sec-fetch-site') == 'cross-site'
                or (origin is not None and origin not in ('http://' + host, 'https://' + host))
                or self._refuse_request(headers) is not None):
            return await reply(writer, 403, {'error': 'same-origin localhost access required'})
        if not access.verify(parts[0], self._http_port, parts[1], headers.get(HEADER.lower())):
            return await reply(writer, 403, {'error': '请从授权客户端打开短信工作台'})
        if parts[0] == 'GET' and path in ('/codec', '/stream.bin', '/audio.bin'):
            if not await prepare_media():
                return
        if path == '/viewer.js':
            screen_stream.VIEWER_JS_TEMPLATE = viewer_script(folder)
        if not special and not restricted:
            return await delegate(ReplayReader(prefix, reader))
        try:
            if path == '/input-health':
                if parts[0] != 'POST':
                    return await reply(writer, 405, {'error': 'POST required'})
                if not active(self):
                    return await reply(writer, 403, {'error': 'device is read-only'})
                length = int(headers.get('content-length', '0'))
                if not 0 < length <= 256:
                    return await reply(writer, 400, {'error': 'invalid health request'})
                if json.loads(await asyncio.wait_for(reader.readexactly(length), 3)) != {}:
                    return await reply(writer, 400, {'error': 'invalid health request'})
                if not await prepare_media():
                    return
                result = await check_input(self, input_lock(self), lambda: active(self))
                return await reply(writer, 200, result)
            if path == '/input-readiness':
                if parts[0] != 'POST':
                    return await reply(writer, 405, {'error': 'POST required'})
                if not device_token or not hmac.compare_digest(headers.get('x-control-token', ''), device_token):
                    return await reply(writer, 403, {'error': 'invalid control token'})
                length = int(headers.get('content-length', '0'))
                if not 0 < length <= 256:
                    return await reply(writer, 400, {'error': 'invalid readiness request'})
                if json.loads(await asyncio.wait_for(reader.readexactly(length), 3)) != {}:
                    return await reply(writer, 400, {'error': 'invalid readiness request'})
                if not await prepare_media():
                    return
                # Readiness probes are authorized by the dashboard token and
                # only send an idle keyboard report; they never inject input.
                result = await check_input(self, input_lock(self), lambda: True)
                return await reply(writer, 200, result)
            if path in ('/manual-touch', '/manual-home', '/manual-key', '/manual-paste', '/manual-composer-focus'):
                if parts[0] != 'POST':
                    return await reply(writer, 405, {'error': 'POST required'})
                length = int(headers.get('content-length', '0'))
                if not 0 < length <= 1024:
                    return await reply(writer, 400, {'error': 'invalid request size'})
                data = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
                if not isinstance(data, dict):
                    return await reply(writer, 400, {'error': 'invalid request'})
                if path in ('/manual-paste', '/manual-composer-focus') and data != {}:
                    return await reply(writer, 400, {'error': 'empty request required'})
                if path == '/manual-touch':
                    if (data.get('type') not in ('contact', 'release')
                            or any(type(data.get(key)) is not int or not 0 <= data[key] <= 65535 for key in ('x', 'y'))
                            or not isinstance(data.get('settle', False), bool)):
                        return await reply(writer, 400, {'error': 'invalid touch'})
                if path == '/manual-key':
                    usages = data.get('usages')
                    if not isinstance(usages, list) or len(usages) > 16 or any(type(key) is not int or not 0 <= key <= 255 for key in usages):
                        return await reply(writer, 400, {'error': 'invalid keyboard usages'})
                generation = getattr(self, '_batch_input_generation', 0)
                if getattr(self, '_batch_recovering', False):
                    return await reply(writer, 503, {'error': '控制连接恢复中，请稍后重新操作'})
                if not active(self):
                    return await reply(writer, 403, {'error': 'device is read-only'})
                if not await prepare_media():
                    return
                async with input_lock(self):
                    if not active(self):
                        return await reply(writer, 403, {'error': 'device is read-only'})
                    if generation != getattr(self, '_batch_input_generation', 0):
                        return await reply(writer, 409, {'error': '控制连接已重建，请重新操作'})
                    async def execute():
                        await self._ensure_hid()
                        if path in ('/manual-touch', '/manual-composer-focus'):
                            # Register the external keyboard before focus can summon
                            # the software keyboard. Warm clicks reuse registration.
                            await self._ensure_keyboard()
                        if path == '/manual-paste':
                            try:
                                return await originals['_handle_key'](self, b'{"usages":[227,25]}')
                            finally:
                                await originals['_handle_key'](self, b'{"usages":[]}')
                        if path == '/manual-composer-focus':
                            from native_conversation import NativeConversation
                            from visual_composer import input_point
                            phone = NativeConversation()
                            phone.base = f'http://127.0.0.1:{self._http_port}'
                            point = await asyncio.to_thread(input_point, phone, fresh=True)
                            if not active(self) or generation != getattr(self, '_batch_input_generation', 0):
                                return 409, b'input connection changed'
                            coords = {key: round(point[key] * 65535) for key in ('x', 'y')}
                            try:
                                code, message = await originals['_handle_touch'](self, json.dumps({'type':'contact', **coords}).encode())
                                if code != 200:
                                    return code, message
                                await asyncio.sleep(.08)
                            finally:
                                await originals['_handle_touch'](self, json.dumps({'type':'release', **coords}).encode())
                            return 200, b'ok'
                        if path == '/manual-home':
                            return await originals['_handle_button'](self, b'{"name":"home","state":"press"}')
                        if path == '/manual-key':
                            return await originals['_handle_key'](self, json.dumps({'usages': usages}).encode())
                        if data['type'] == 'release' and data.get('settle'):
                            contact = json.dumps({'type': 'contact', 'x': data['x'], 'y': data['y']}).encode()
                            code, message = await originals['_handle_touch'](self, contact)
                            if code != 200:
                                return code, message
                            await asyncio.sleep(.08)
                            await originals['_handle_touch'](self, contact)
                        payload = json.dumps({key: data[key] for key in ('type', 'x', 'y')}).encode()
                        return await originals['_handle_touch'](self, payload)
                    try:
                        code, _ = await asyncio.wait_for(execute(), 12 if path == '/manual-composer-focus' else 4)
                        if code == 200:
                            kind = {'/manual-touch': '_handle_touch', '/manual-key': '_handle_key', '/manual-home': '_handle_button', '/manual-paste': '_handle_key', '/manual-composer-focus': '_handle_touch'}[path]
                            record_input(self, kind, {'type':'release'} if path == '/manual-composer-focus' else data)
                    except Exception:
                        await clear_input(self)
                        raise
                return await reply(writer, code, {'ok': code == 200})
            if path == '/jpeg.bin':
                if parts[0] != 'GET':
                    return await reply(writer, 405, {'error': 'GET required'})
                from video_compat import serve_jpeg
                return await serve_jpeg(self._http_port, writer, self, reader=reader)
            if path == '/translation':
                if parts[0] not in ('GET', 'POST'):
                    return await reply(writer, 405, {'error': 'GET or POST required'})
                if parts[0] == 'POST' and not active(self):
                    return await reply(writer, 403, {'error': 'device is read-only'})
                if parts[0] == 'GET':
                    body = {'action':'status'}
                else:
                    length = int(headers.get('content-length', '0'))
                    if not 0 < length <= 3*1024*1024:
                        return await reply(writer, 413, {'error':'request too large'})
                    body = json.loads(await asyncio.wait_for(reader.readexactly(length), 10))
                    if not isinstance(body, dict):
                        return await reply(writer, 400, {'error':'invalid request'})
                from translation_routes import request
                from translation import TranslationError
                try:
                    result = await asyncio.to_thread(request, os.environ.get('PYMOBILEDEVICE3_UDID', 'single-device'), body)
                    return await reply(writer, 200, result)
                except TranslationError as exc:
                    return await reply(writer, 200, {'error':str(exc)})
            if path == '/control-mode':
                if not device_token or not hmac.compare_digest(headers.get('x-control-token', ''), device_token):
                    return await reply(writer, 403, {'error': 'invalid control token'})
                if parts[0] == 'GET':
                    return await reply(writer, 200, {'active': active(self)})
                if parts[0] != 'POST':
                    return await reply(writer, 405, {'error': 'POST required'})
                length = int(headers.get('content-length', '0'))
                if not 0 < length <= 256:
                    return await reply(writer, 400, {'error': 'invalid mode'})
                body = json.loads(await asyncio.wait_for(reader.readexactly(length), 3))
                if not isinstance(body, dict) or not isinstance(body.get('active'), bool):
                    return await reply(writer, 400, {'error': 'invalid mode'})
                async with input_lock(self):
                    self._batch_active = False
                    while not self._hid_queue.empty():
                        self._hid_queue.get_nowait()
                    try:
                        contact = getattr(self, '_batch_contact', None)
                        if contact is not None:
                            await originals['_handle_touch'](self, json.dumps({**contact, 'type':'release'}).encode())
                            self._batch_contact = None
                        if self._uhs is not None and self._kb_service_id is not None:
                            await self._uhs.send_keyboard(self._kb_service_id, [])
                        self._batch_keys_down = False
                    except Exception:
                        await clear_input(self)
                    self._batch_active = body['active']
                return await reply(writer, 200, {'active': active(self)})
            if restricted and not active(self):
                return await reply(writer, 403, {'error': 'device is read-only'})
            if not special:
                return await delegate(ReplayReader(prefix, reader))
            if path == '/device-clipboard-info':
                if parts[0] != 'GET':
                    return await reply(writer, 405, {'error': 'GET required'})
                from pymobiledevice3.remote.core_device.pasteboard_service import PasteboardService, POLICY_PROMISE_SECONDARY, PasteboardContent
                async with PasteboardService(self._rsd) as service:
                    snapshot = await asyncio.wait_for(service.get(data_policy=POLICY_PROMISE_SECONDARY), 8)
                board = snapshot.get('pasteboard', snapshot)
                items = []
                for item in board.get('items', []):
                    data = item.get('data', {})
                    items.append({'types': item.get('types', []), 'representations': {
                        key: {'inline_bytes': len(value.get('data', b'')),
                              'promised': value.get('isPromised', False),
                              'available': value.get('isAvailable', None)}
                        for key, value in data.items() if isinstance(value, dict)}})
                import plistlib
                archive_schema = []
                for item in board.get('items', []):
                    raw = item.get('data', {}).get('com.apple.uikit.attributedstring', {}).get('data')
                    if not isinstance(raw, bytes):
                        continue
                    try:
                        archive = plistlib.loads(raw)
                        objects = archive.get('$objects', [])
                        archive_schema = [{'kind': type(value).__name__,
                            'keys': list(value) if isinstance(value, dict) else [],
                            'string_length': len(value) if isinstance(value, str) else None}
                            for value in objects]
                    except Exception:
                        archive_schema = [{'kind': 'unparsed', 'bytes': len(raw)}]
                content = PasteboardContent.from_snapshot(snapshot)
                return await reply(writer, 200, {'items': items,
                    'archive_schema': archive_schema, 'text_detected': content.text is not None,
                    'text_length': len(content.text) if content.text is not None else 0})
            if parts[0] == 'GET':
                content = await asyncio.to_thread(windows_clipboard, include_image=True)
                return await reply(writer, 200, content)
            if parts[0] != 'POST':
                return await reply(writer, 405, {'error': 'GET or POST required'})
            if not headers.get('content-type', '').startswith('application/json'):
                return await reply(writer, 400, {'error': 'JSON required'})
            length = int(headers.get('content-length', '0'))
            if not 0 < length <= MAX_TEXT_BYTES:
                return await reply(writer, 413, {'error': 'text exceeds size limit'})
            body = json.loads(await asyncio.wait_for(reader.readexactly(length), 5))
            text = body.get('text') if isinstance(body, dict) else None
            if not isinstance(text, str) or '\x00' in text:
                return await reply(writer, 400, {'error': 'valid text required'})
            async with input_lock(self):
                if not active(self):
                    return await reply(writer, 403, {'error': 'device is read-only'})
                await asyncio.to_thread(windows_clipboard, text, write=True)
            return await reply(writer, 200, {'ok': True})
        except asyncio.TimeoutError:
            if path in ('/manual-touch', '/manual-home', '/manual-key', '/manual-paste', '/manual-composer-focus'):
                return await reply(writer, 503, {'error': '控制请求未完成，请核对手机后重新操作'})
            return await reply(writer, 400, {'error': 'invalid request'})
        except (ValueError, asyncio.IncompleteReadError):
            return await reply(writer, 400, {'error': 'invalid request'})
        except Exception:
            if path in ('/manual-touch', '/manual-home', '/manual-key', '/manual-paste', '/manual-composer-focus'):
                logging.getLogger(__name__).exception('Manual phone control failed: %s', path)
                # Never replay an input: a failed release may already have sent.
                return await reply(writer, 500, {'error': '手机触控服务不可用，请检查连接和开发者服务'})
            return await reply(writer, 500, {'error': 'Windows clipboard unavailable; retry'})

    async def handle(self, reader, writer):
        ensure_idle_monitor(self, input_lock(self))
        # asyncio keeps weak references to tasks. Retain connection handlers
        # while they await device responses, including long-lived video streams.
        tasks = getattr(self, '_viewer_http_tasks', None)
        if tasks is None:
            tasks = self._viewer_http_tasks = set()
        task = asyncio.current_task()
        tasks.add(task)
        try:
            return await dispatch_handle(self, reader, writer)
        finally:
            tasks.discard(task)
            if not writer.is_closing():
                writer.close()

    screen_stream.ScreenStreamServer._handle_http = handle
