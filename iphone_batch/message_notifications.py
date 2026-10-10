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
    captions = [i.caption or '' for i in items]
    return ('Notification Center, Header' in captions or 'Show Notifications, Button' in captions
            or ('Flashlight, Off, Button' in captions and 'Camera, Button' in captions))


async def elements(service):
    items = await scan(service, limit=1000, seconds=18, settle=0)
    if not items.complete:
        items = await scan(service, limit=1000, seconds=18, settle=.04)
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
    before = await elements(service)
    if is_center(before):
        return before, False
    preserve_draft(before)
    await swipe(phone, .002, .82)
    current = await elements(service)
    if not is_center(current):
        raise ValueError('未确认通知中心，未点击任何通知')
    return current, True


async def discover(service, phone, device):
    items, opened = await enter_center(service, phone)
    try:
        notifications = [row for item in items
                         if (row:=parse_notification(item.caption, item.platform_identifier, device))]
        return {'items':notifications, 'complete':True,
                'scope':'仅读取 Messages 通知；其他 App 通知已跳过，消息完整性需进入会话核对'}
    finally:
        if opened:
            await swipe(phone, .995, .20)


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
            await swipe(phone, .995, .20)
        raise
