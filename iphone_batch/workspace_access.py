"""Authenticate the translator's main process and trusted local backend calls."""
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.request
from urllib.parse import urlsplit

HEADER = 'X-Pikachu-Workspace-Auth'
_key = None
_key_lock = threading.Lock()

def load_key():
    global _key
    with _key_lock:
        if _key is not None:
            return _key
        parent = os.environ.get('LOCALAPPDATA')
        if not parent:
            raise RuntimeError('缺少本机用户数据目录，无法启用授权客户端访问校验')
        path = Path(parent) / 'PikachuSmsBridge' / 'workspace-access.key'
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('x', encoding='ascii') as output:
                output.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        for attempt in range(10):
            raw = path.read_text(encoding='ascii').strip()
            if re.fullmatch('[0-9a-f]{64}', raw):
                _key = bytes.fromhex(raw)
                return _key
            if attempt < 9:
                time.sleep(.02)
        raise RuntimeError('本机访问凭据损坏，已拒绝开放工作台')

def payload(method, port, target, timestamp, nonce):
    return f'v1\n{method.upper()}\n{port}\n{target}\n{timestamp}\n{nonce}'.encode('utf-8')

def signed_header(method, url, *, key=None, timestamp=None, nonce=None):
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password:
        raise ValueError('Only loopback workspace requests may be signed')
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or secrets.token_hex(16)
    target = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
    digest = hmac.new(key if key is not None else load_key(), payload(method, parsed.port or 80, target, timestamp, nonce), hashlib.sha256).hexdigest()
    return f'v1:{timestamp}:{nonce}:{digest}'

class AccessVerifier:
    def __init__(self, key=None):
        self.key = key if key is not None else load_key()
        self.seen = {}
        self.lock = threading.Lock()

    def verify(self, method, port, target, header, now=None):
        if not isinstance(header, str) or len(header) > 160:
            return False
        parts = header.split(':')
        if len(parts) != 4:
            return False
        version, timestamp, nonce, digest = parts
        if version != 'v1' or not re.fullmatch('[0-9]{1,12}', timestamp) or not re.fullmatch('[0-9a-f]{32}', nonce) or not re.fullmatch('[0-9a-f]{64}', digest):
            return False
        now = time.time() if now is None else now
        if abs(now - int(timestamp)) > 30:
            return False
        expected = hmac.new(self.key, payload(method, port, target, timestamp, nonce), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, digest):
            return False
        with self.lock:
            if nonce in self.seen:
                return False
            self.seen = {n: expiry for n, expiry in self.seen.items() if expiry >= now}
            self.seen[nonce] = now + 61
        return True

class _SignedRequests(urllib.request.BaseHandler):
    def http_request(self, request):
        parsed = urlsplit(request.full_url)
        if parsed.scheme == 'http' and parsed.hostname == '127.0.0.1':
            request.add_header(HEADER, signed_header(request.get_method(), request.full_url))
        return request

def signed_opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _SignedRequests())
