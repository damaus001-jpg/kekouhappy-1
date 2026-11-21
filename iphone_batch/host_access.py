"""Short-lived, installation-bound grants for Pikachu backend control.

This is an application entry restriction, not a boundary against the same
Windows user reading their own key or changing their installation.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

from workspace_access import load_key

PROJECT = Path(__file__).resolve().parents[1]
POLICY = '8070-host-policy.json'
_operation = ContextVar('pikachu_8070_operation', default=None)


class AuthorizationError(RuntimeError):
    def __init__(self):
        super().__init__('请通过皮卡丘操作8070后台')


class InstallationError(RuntimeError):
    def __init__(self):
        super().__init__('安装文件缺失')


def canonical_root(root):
    return str(Path(root).resolve()).replace('\\', '/').lower().rstrip('/')


def host_only(root=PROJECT):
    policy = Path(root) / POLICY
    if not policy.exists():
        return False
    try:
        data = json.loads(policy.read_text(encoding='utf-8-sig'))
        if data != {'protocol': 1, 'mode': 'pikachu-only'}:
            raise ValueError('Invalid host policy')
    except (OSError, ValueError, TypeError):
        raise InstallationError() from None
    return True


def signing_payload(action, root, timestamp, nonce):
    return f'pikachu-8070-control-v1\n{action}\n{canonical_root(root)}\n{timestamp}\n{nonce}'.encode('utf-8')


def make_proof(action, root=PROJECT, *, key=None, timestamp=None, nonce=None):
    if action not in ('status', 'start', 'stop', 'serve'):
        raise ValueError('Unsupported backend action')
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or secrets.token_hex(16)
    signature = hmac.new(key if key is not None else load_key(),
                         signing_payload(action, root, stamp, nonce), hashlib.sha256).hexdigest()
    return {'v': 1, 'timestamp': stamp, 'nonce': nonce, 'signature': signature}


def verify_proof(action, proof, root=PROJECT, *, key=None, now=None):
    if action not in ('status', 'start', 'stop', 'serve') or not isinstance(proof, dict):
        raise AuthorizationError()
    stamp, nonce, signature = (proof.get(name) for name in ('timestamp', 'nonce', 'signature'))
    if (type(proof.get('v')) is not int or proof['v'] != 1 or
            not isinstance(stamp, str) or not re.fullmatch(r'[0-9]{1,12}', stamp) or
            not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{32}', nonce) or
            not isinstance(signature, str) or not re.fullmatch('[0-9a-f]{64}', signature)):
        raise AuthorizationError()
    clock = time.time() if now is None else now
    if abs(clock - int(stamp)) > 30:
        raise AuthorizationError()
    expected = hmac.new(key if key is not None else load_key(),
                        signing_payload(action, root, stamp, nonce), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AuthorizationError()
    used = Path(root) / 'iphone_batch/.device-data/logs/host-control/nonces'
    used.mkdir(parents=True, exist_ok=True)
    # Atomic across separate CLI invocations, including concurrent replays.
    try:
        descriptor = os.open(used / (nonce + '.used'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise AuthorizationError() from None
    os.close(descriptor)
    for entry in used.glob('*.used'):
        try:
            if entry.stat().st_mtime < clock - 120:
                entry.unlink()
        except OSError:
            pass


def read_proof(stream=None):
    source = sys.stdin if stream is None else stream
    if source is None or source.isatty():
        raise AuthorizationError()
    try:
        line = source.readline(4097)
        if not line or len(line) > 4096:
            raise ValueError('Missing or oversized grant')
        return json.loads(line)
    except (ValueError, OSError, UnicodeError):
        raise AuthorizationError() from None


@contextmanager
def authorized_operation(action, proof, root=PROJECT):
    verify_proof(action, proof, root)
    token = _operation.set((action, canonical_root(root)))
    try:
        yield
    finally:
        _operation.reset(token)


def require_backend_action(action, root=PROJECT):
    if host_only(root) and _operation.get() != (action, canonical_root(root)):
        raise AuthorizationError()


def require_dashboard_launch(root=PROJECT):
    if host_only(root):
        verify_proof('serve', read_proof(), root)
