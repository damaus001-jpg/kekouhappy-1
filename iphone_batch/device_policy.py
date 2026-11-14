"""Local allowlist for workspace device connections; no external project dependency."""
import json
import re
import uuid
from pathlib import Path


def load_enabled(path):
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = data.get('enabled_udids') if isinstance(data, dict) else None
    if (not isinstance(rows, list) or any(not isinstance(x, str)
            or not re.fullmatch(r'[A-Za-z0-9-]+', x) for x in rows)):
        raise ValueError('设备启用名单无效，已停止启动，避免连接停用设备')
    return frozenset(rows)


def permitted(rows, enabled):
    return [row for row in rows if enabled is None or row['udid'] in enabled]


def connection_allowed(device, enabled):
    return enabled is None or device['udid'] in enabled


def require_connection(device, enabled):
    if not connection_allowed(device, enabled):
        raise ValueError('该设备已停用，未建立手机连接')


def load_transport(path):
    path = Path(path)
    if not path.exists():
        return 'tunneld'
    data = json.loads(path.read_text(encoding='utf-8'))
    value = data.get('transport', 'tunneld')
    if value not in ('tunneld', 'userspace'):
        raise ValueError('设备连接路径配置无效')
    return value


def load_readonly(path):
    path = Path(path)
    if not path.exists():
        return frozenset()
    data = json.loads(path.read_text(encoding='utf-8'))
    rows = data.get('readonly_udids', [])
    if not isinstance(rows, list) or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9-]+', x) for x in rows):
        raise ValueError('仅监看名单无效，已停止启动')
    return frozenset(rows)


def save_access(path, enabled, readonly):
    """Caller serializes updates; preserve transport and unrelated preferences."""
    path = Path(path)
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError('设备连接配置无效')
    for rows in (enabled, readonly):
        if any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9-]+', x) for x in rows):
            raise ValueError('设备标识无效')
    data.update(enabled_udids=sorted(enabled), readonly_udids=sorted(readonly))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def input_allowed(udid, path):
    """Live worker-side guard; malformed policy locks input without stopping video."""
    try:
        enabled=load_enabled(path)
        return (enabled is None or udid in enabled) and udid not in load_readonly(path)
    except (OSError,ValueError,TypeError,AttributeError):
        return False
