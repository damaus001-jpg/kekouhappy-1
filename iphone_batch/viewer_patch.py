"""Local viewer assets and a same-origin, loopback-only Windows text clipboard bridge."""
import asyncio
import json
import os
import hmac
import time
from pathlib import Path

MAX_TEXT_BYTES = 1024 * 1024


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


def windows_clipboard(text=None, *, write=False):
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
        if not clipboard.IsClipboardFormatAvailable(clipboard.CF_UNICODETEXT):
            return None
        return clipboard.GetClipboardData(clipboard.CF_UNICODETEXT)
    finally:
        clipboard.CloseClipboard()


async def reply(writer, code, data):
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    reason = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 405: 'Method Not Allowed',
              413: 'Payload Too Large', 500: 'Internal Server Error'}[code]
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
    screen_stream.VIEWER_JS_TEMPLATE = (folder / 'viewer.js').read_bytes() + b'\n' + (folder / 'translation.js').read_bytes()
    if getattr(screen_stream.ScreenStreamServer, '_batch_patched', False):
        return
    screen_stream.ScreenStreamServer._batch_patched = True
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
    for name, original_action in originals.items():
        def wrap_action(action, kind):
            async def guarded(instance, body):
                async with input_lock(instance):
                    if not active(instance):
                        return 403, b'device is read-only'
                    result = await action(instance, body)
                    if kind == '_handle_touch' and result[0] == 200:
                        data = json.loads(body)
                        instance._batch_contact = data if data['type'] == 'contact' else None
                    return result
            return guarded
        setattr(screen_stream.ScreenStreamServer, name, wrap_action(original_action, name))
    original = screen_stream.ScreenStreamServer._handle_http

    async def dispatch_handle(self, reader, writer):
        first = await reader.readline()
        parts = first.decode('latin-1').strip().split()
        if len(parts) != 3:
            return await original(self, ReplayReader(first, reader), writer)
        device_token = token_for(self)
        path = parts[1].partition('?')[0]
        special = path in ('/host-clipboard', '/device-clipboard-info', '/control-mode', '/translation')
        restricted = device_token and (parts[0] == 'POST' or path.startswith('/clipboard') or path == '/host-clipboard')
        if not special and not restricted:
            return await original(self, ReplayReader(first, reader), writer)
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
        try:
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
                    contact = getattr(self, '_batch_contact', None)
                    if contact is not None:
                        await originals['_handle_touch'](self, json.dumps({**contact, 'type':'release'}).encode())
                        self._batch_contact = None
                    if self._uhs is not None and self._kb_service_id is not None:
                        await self._uhs.send_keyboard(self._kb_service_id, [])
                    self._batch_active = body['active']
                return await reply(writer, 200, {'active': active(self)})
            if restricted and not active(self):
                return await reply(writer, 403, {'error': 'device is read-only'})
            if not special:
                return await original(self, ReplayReader(prefix, reader), writer)
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
                text = await asyncio.to_thread(windows_clipboard)
                return await reply(writer, 200, {'text': text})
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
        except (ValueError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            return await reply(writer, 400, {'error': 'invalid request'})
        except Exception:
            return await reply(writer, 500, {'error': 'Windows clipboard unavailable; retry'})

    async def handle(self, reader, writer):
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
