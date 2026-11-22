"""Observe one live SpringBoard banner without gestures or UI activation."""
import asyncio
import hashlib
import json
import struct


def parse_banner(label, token, device):
    from native_conversation import phone_key
    parts = label.split(', ', 3) if isinstance(label, str) else []
    if len(parts) != 4 or parts[0].upper() not in {'MESSAGES', '信息', '短信'}:
        return None
    _, when, sender, preview = parts
    identifier = hashlib.sha256(json.dumps([device, token.hex(), sender, preview], ensure_ascii=False).encode()).hexdigest()
    return {'id':identifier, 'device':device, 'app':'Messages', 'sender':sender,
            'phone_number':phone_key(sender), 'preview':preview, 'time':when,
            'element_id':token.hex(), 'caption':label, 'clickable':False,
            'source':'banner', 'scope':'notification_preview'}


async def observe(service, lockdown, device):
    from pymobiledevice3.services.os_trace import OsTraceService
    from pymobiledevice3.services.accessibilityaudit import deserialize_object
    async with OsTraceService(lockdown) as trace:
        processes = (await asyncio.wait_for(trace.get_pid_list(), 3))['Payload']
    pid = next((int(pid) for pid, row in processes.items() if row.get('ProcessName') == 'SpringBoard'), None)
    if pid is None:
        raise ValueError('无法定位当前系统通知进程')
    await service._ensure_ready()
    await service.set_app_monitoring_enabled(False)
    await service.set_monitored_event_type()
    original = deserialize_object(await asyncio.wait_for(service._invoke('deviceFetchSpecialElement:', 0), 2))
    original_token = getattr(original, 'identifier', None)
    if not isinstance(original_token, bytes) or len(original_token) < 4:
        raise ValueError('无法核验检查器恢复目标，已跳过横幅读取')
    original_pid = struct.unpack('<I', original_token[:4])[0]
    try:
        await service._invoke('deviceSetAuditTargetPid:', pid, expects_reply=False)
        banner = deserialize_object(await asyncio.wait_for(service._invoke('deviceFetchSpecialElement:', 1), 2))
        row = None
        if getattr(banner, '_fields', {}).get('AccessibilityIdentifier_v1') == 'NotificationShortLookView':
            token = getattr(banner, 'identifier', None)
            if isinstance(token, bytes):
                await service._invoke('deviceInspectorFocusOnElement:', service._serialize_element(token), expects_reply=False)
                label = await asyncio.wait_for(service.element_attribute(token, 'Label'), 2)
                if not isinstance(label, str) or not label.strip():
                    await asyncio.sleep(.05)
                    label = await asyncio.wait_for(service.element_attribute(token, 'Label'), 2)
                if not isinstance(label, str) or not label.strip():
                    raise ValueError('横幅存在但预览尚未可读')
                row = parse_banner(label, token, device)
        return {'device':device, 'source':'banner', 'scope':'observed_previews',
                'complete':False, 'items':[row] if row else []}
    finally:
        await service._invoke('deviceSetAuditTargetPid:', original_pid, expects_reply=False)
        await service.set_app_monitoring_enabled(False)
