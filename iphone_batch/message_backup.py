"""Read completed local message snapshots; optionally request a USB backup."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re
import sqlite3
import sys


def attributed_text(blob):
    from typedstream import unarchive_from_data
    from typedstream.types.foundation import NSString
    value = unarchive_from_data(blob)
    while value is not None:
        for item in getattr(value, 'contents', []):
            string = getattr(item, 'value', item)
            if isinstance(string, NSString):
                return string.value
        value = getattr(value, 'super_object', None)
    raise ValueError('未解析的消息正文')


def identifier(value):
    if re.fullmatch(r'[+\d\s().-]+', value or ''):
        digits = re.sub(r'\D', '', value)
        return '+' + digits if value.strip().startswith('+') else digits
    return value


def read_snapshot(root, device, contact):
    if not re.fullmatch(r'[A-Za-z0-9-]+', device):
        raise ValueError('设备标识无效')
    folder = Path(root) / 'sms-backup' / device
    status_path = folder / 'Status.plist'
    if not status_path.exists():
        return None
    status = plistlib.loads(status_path.read_bytes())
    manifest = plistlib.loads((folder / 'Manifest.plist').read_bytes())
    if status.get('SnapshotState') != 'finished':
        raise ValueError('数据库快照尚未完成')
    if manifest.get('IsEncrypted'):
        raise ValueError('数据库快照已加密，需要原备份密码')
    file_id = hashlib.sha1(b'HomeDomain-Library/SMS/sms.db').hexdigest()
    database = folder / file_id[:2] / file_id
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('消息数据库完整性检查失败')
        chats = [r['ROWID'] for r in db.execute('SELECT ROWID,chat_identifier FROM chat')
                 if identifier(r['chat_identifier']) == identifier(contact)]
        if not chats:
            return None
        marks = ','.join('?' for _ in chats)
        rows = db.execute(f'''SELECT DISTINCT m.ROWID,m.guid,m.text,m.attributedBody,
            m.is_from_me,m.is_read,m.date,m.service,m.cache_has_attachments,
            m.item_type,m.associated_message_type
            FROM message m JOIN chat_message_join j ON j.message_id=m.ROWID
            WHERE j.chat_id IN ({marks}) ORDER BY m.date,m.ROWID''', chats).fetchall()
    messages = []
    for row in rows:
        text, decode_error = row['text'], None
        if text is None and row['attributedBody']:
            try:
                text = attributed_text(row['attributedBody'])
            except Exception as exc:
                decode_error = str(exc)
        kind = ('reaction' if row['associated_message_type'] else 'system' if row['item_type']
                else 'attachment' if not text and row['cache_has_attachments'] else 'text')
        try:
            timestamp = (datetime(2001, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=row['date']/1e9)).isoformat()
        except (OverflowError, TypeError):
            timestamp = None
        message = {'message_id': device + ':db:' + str(row['ROWID']),
                   'database_id': row['ROWID'], 'guid': row['guid'], 'text': text or '',
                   'side': 'outgoing' if row['is_from_me'] else 'incoming',
                   'is_read': bool(row['is_read']), 'read_state_source': 'backup-snapshot',
                   'time': timestamp, 'kind': kind, 'transport': row['service'],
                   'has_attachments': bool(row['cache_has_attachments']), 'record_source': 'backup-snapshot'}
        if decode_error:
            message['decode_error'] = decode_error
        messages.append(message)
    return {'messages': messages,
            'snapshot_at': datetime.fromtimestamp(status_path.stat().st_mtime, timezone.utc).isoformat(),
            'scope': '已完成备份中的会话记录；未读状态仅对应备份时刻'}


async def refresh_snapshot(root, device):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service, BackupSelection
    from pymobiledevice3 import common
    common._HOMEFOLDER = Path(root)
    folder = Path(root) / 'sms-backup'
    folder.mkdir(parents=True, exist_ok=True)
    lockdown = await create_using_usbmux(serial=device, connection_type='USB',
        usbmux_address='127.0.0.1:27015', pairing_records_cache_folder=Path(root), autopair=False)
    try:
        async with asyncio.timeout(180):
            async with Mobilebackup2Service(lockdown) as service:
                await service.backup(full=False, backup_directory=folder,
                    filter_callback=service.selection_filter_callback(BackupSelection.SMS.rules()))
    finally:
        await lockdown.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True)
    parser.add_argument('--contact', required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    try:
        if not re.fullmatch(r'[A-Za-z0-9-]+', args.device):
            raise ValueError('设备标识无效')
        if args.refresh:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            asyncio.run(refresh_snapshot(args.root, args.device))
        print(json.dumps({'snapshot': read_snapshot(args.root, args.device, args.contact)}, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True))
        sys.exit(1)
