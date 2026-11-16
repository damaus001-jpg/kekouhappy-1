"""Discover and activate freshly identified Messages notifications only."""
import asyncio
import hashlib
import json
from native_conversation import phone_key
from native_ui_scan import scan
from native_action import serialize

SOURCE_NAMES = {'MESSAGES', '信息', '短信'}


def parse_notification(caption, element_id, device):
    parts = (caption or '').split(', ')
    if not parts or parts[0].upper() not in SOURCE_NAMES or 'Button' not in parts:
        return None
    grouped = len(parts)>1 and parts[1]=='Grouped'
    position = 2 if grouped else 1
    if len(parts) < position+4:
        return None
    when = parts[position]
    position += 1
    # Yesterday notifications have a separate time field.
    import re
    if position < len(parts) and re.fullmatch(r'\d{1,2}:\d{2}', parts[position]):
        when += ', '+parts[position]
        position += 1
    sender = parts[position]
    body = parts[position+1:]
    if body and body[-1]=='Activate to expand':
        body.pop()
    if body and body[-1]=='Button':
        body.pop()
    preview = ', '.join(body)
    phone = phone_key(sender)
    # Time labels change without a new message. Do not include them in identity.
    identity = hashlib.sha256(json.dumps([device, element_id, sender, preview], ensure_ascii=False).encode()).hexdigest()
    return {'id':identity, 'device':device, 'app':'Messages', 'sender':sender,
            'phone_number':phone, 'preview':preview, 'time':when, 'grouped':grouped,
            'element_id':element_id, 'clickable':bool(phone), 'caption':caption}


def is_center(items):
    # AX identities only. A title or a successful swipe is never sufficient.
    flashlight_names = {'Flashlight, Off, Button', 'Flashlight, On, Button', 'Flashlight, Button',
        '手电筒, 关闭, Button', '手电筒, 开启, Button', '手电筒, Button',
        '手电筒, 关闭, 按钮', '手电筒, 开启, 按钮', '手电筒, 按钮'}
    camera_names = {'Camera, Button', '相机, Button', '相机, 按钮'}
    flashlights = {i.platform_identifier for i in items if (i.caption or '') in flashlight_names}
    cameras = {i.platform_identifier for i in items if (i.caption or '') in camera_names}
    return len(flashlights) == len(cameras) == 1 and flashlights.isdisjoint(cameras)


def is_messages_list(items):
    return any((item.caption or '') in ('Messages, Header', '信息, Header', '短信, Header') for item in items)


async def probe_surface(service, *, reverse=False):
    """Inspect a few landmarks; never use a full page scan to discover its type."""
    observed = []
    empty = {'Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS'}
    def enough(item):
        observed.append(item)
        captions = [entry.caption or '' for entry in observed]
        return (is_center(observed) or is_messages_list(observed)
                or any(c in empty for c in captions)
                or (any(c.startswith('Send, Button') for c in captions)
                    and any(c.startswith('Message, ') for c in captions)))
    items = await scan(service, limit=12, seconds=1.2, settle=0,
                       reverse=reverse, stop_when=enough)
    if items.reason not in ('target_found', 'cycle_verified', 'limit'):
        raise ValueError('无法快速核验当前页面，已停止通知检查，未执行完整遍历')
    return items


async def verified_center_page(service):
    items = await elements(service, center_only=True)
    if not is_center(items):
        raise ValueError('通知检查期间页面发生变化，未更新通知结果')
    return items


async def elements(service, *, center_only=False):
    def wrong_surface(item):
        caption = item.caption or ''
        return center_only and (is_messages_list([item]) or ', Show Conversation Details, Button' in caption
                                or ', 显示对话详细信息, 按钮' in caption)
    items = await scan(service, limit=1000, seconds=18, settle=0, stop_when=wrong_surface if center_only else None)
    if center_only and any(wrong_surface(item) for item in items):
        raise ValueError('页面已离开通知中心，已停止遍历，未更新通知结果')
    if not items.complete:
        items = await scan(service, limit=1000, seconds=18, settle=.04, stop_when=wrong_surface if center_only else None)
        if center_only and any(wrong_surface(item) for item in items):
            raise ValueError('页面已离开通知中心，已停止遍历，未更新通知结果')
    if not items.complete:
        raise ValueError(f'通知遍历尚未完成（{items.reason}，{len(items)} 个元素），未更新发现进度')
    return items


async def swipe(phone, start, end):
    try:
        for step in range(25):
            phone.request(phone.base, '/touch', {'type':'contact','x':32768,
                'y':round((start+(end-start)*step/24)*65535)})
            await asyncio.sleep(.025)
    finally:
        phone.request(phone.base, '/touch', {'type':'release','x':32768,'y':round(end*65535)})
    await asyncio.sleep(.5)


def preserve_draft(items):
    captions = [i.caption or '' for i in items]
    if any(c.startswith('Send, Button') for c in captions) and any(c.startswith('Message, ') for c in captions):
        raise ValueError('手机有未发送草稿，已暂停通知检查与会话切换')


async def enter_center(service, phone):
    before = await probe_surface(service)
    if is_center(before):
        return await verified_center_page(service), False
    preserve_draft(before)
    if not is_messages_list(before):
        footer = await probe_surface(service, reverse=True)
        preserve_draft(footer)
        if is_center(list(before) + list(footer)):
            return await verified_center_page(service), False
    await swipe(phone, .002, .82)
    current = await probe_surface(service)
    if not is_center(current) and not is_messages_list(current):
        footer = await probe_surface(service, reverse=True)
        current = list(current) + list(footer)
    if not is_center(current):
        raise ValueError('下拉后未确认通知中心，已停止检查；未完整遍历当前页面，未更新通知结果')
    return await verified_center_page(service), True


async def close_center_if_current(service, phone):
    try:
        current = await probe_surface(service, reverse=True)
    except ValueError:
        return
    if is_center(current):
        await swipe(phone, .995, .20)


async def discover(service, phone, device):
    items, opened = await enter_center(service, phone)
    try:
        notifications = [row for item in items
                         if (row:=parse_notification(item.caption, item.platform_identifier, device))]
        return {'items':notifications, 'complete':True,
                'scope':'仅读取 Messages 通知；其他 App 通知已跳过，消息完整性需进入会话核对'}
    finally:
        if opened:
            await close_center_if_current(service, phone)


async def activate(service, item):
    actions = [attribute._fields for section in item._fields.get('InspectorSectionsValue_v1', [])
               for attribute in section._fields.get('ElementAttributesValue_v1', [])
               if attribute._fields.get('AttributeNameValue_v1')=='AXAction-2010'
               and attribute._fields.get('PerformsActionValue_v1')]
    if len(actions)!=1:
        raise ValueError('通知没有唯一原生激活动作，未点击')
    await service._invoke('deviceElement:performAction:withValue:',
        serialize('AXAuditElement_v1', {'PlatformElementValue_v1':item.element.identifier}),
        serialize('AXAuditElementAttribute_v1', actions[0]), 0, expects_reply=False)
    await asyncio.sleep(.6)


async def open_notification(service, phone, device, expected, context_reader):
    if expected.get('device')!=device or not expected.get('phone_number'):
        raise ValueError('通知设备或完整号码未核验')
    items, opened = await enter_center(service, phone)
    try:
        for attempt in range(3):
            candidates = []
            for item in items:
                row = parse_notification(item.caption, item.platform_identifier, device)
                if row and row['phone_number']==expected['phone_number'] and row['preview']==expected['preview']:
                    if attempt or row['id']==expected['id']:
                        candidates.append((item,row))
            if len(candidates)!=1:
                raise ValueError('短信通知已变化或目标不唯一，请刷新通知')
            target, row = candidates[0]
            await activate(service, target)
            items = await elements(service)
            unchanged = [fresh for item in items
                if (fresh:=parse_notification(item.caption,item.platform_identifier,device))
                and fresh['id']==row['id'] and fresh['grouped']==row['grouped']]
            if unchanged:
                from notification_touch import tap_notification
                await tap_notification(service,phone,device,unchanged[0])
                items = await elements(service)
            captions = [i.caption or '' for i in items]
            if any(', Show Conversation Details, Button' in c for c in captions):
                current = context_reader([{'caption':i.caption or '', 'platform_identifier':i.platform_identifier} for i in items])
                if current.get('phone_number')!=expected['phone_number']:
                    raise ValueError('通知打开的收件人不一致，未允许回复')
                preserve_draft(items)
                return {'device':device, **current}
            if not row['grouped'] and attempt==2:
                raise ValueError('点击通知后未确认进入 Messages 会话')
        raise ValueError('分组通知尚未打开会话，请在手机检查')
    except Exception:
        if opened and is_center(items):
            await close_center_if_current(service, phone)
        raise
