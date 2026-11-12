"""JSON worker for native desktop features. No browser, screenshots or OCR."""
import asyncio
import contextlib
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time
import uuid

DATA = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA.parent))


def exact(sock, size):
    out = bytearray()
    while len(out) < size:
        chunk = sock.recv(size - len(out))
        if not chunk:
            raise ConnectionError('VNC 连接已断开')
        out.extend(chunk)
    return bytes(out)


class Input:
    def __init__(self, port):
        from pymobiledevice3.remote.core_device.vnc_server import vnc_auth_response
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=8)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        exact(self.sock, 12)
        self.sock.sendall(b'RFB 003.008\n')
        types = exact(self.sock, exact(self.sock, 1)[0])
        if 2 not in types:
            raise ValueError('VNC 认证类型不兼容')
        self.sock.sendall(b'\x02')
        self.sock.sendall(vnc_auth_response('isolated', exact(self.sock, 16)))
        if struct.unpack('>I', exact(self.sock, 4))[0]:
            raise ValueError('VNC 认证失败')
        self.sock.sendall(b'\x01')
        init = exact(self.sock, 24)
        self.width, self.height = struct.unpack('>HH', init[:4])
        exact(self.sock, struct.unpack('>I', init[20:24])[0])
        self.sock.settimeout(1)
        self.stopping = threading.Event()
        self.clipboard_ready = threading.Event()
        self.receive_error = None
        self.receiving = threading.Thread(target=self.drain, daemon=True)
        self.receiving.start()

    def drain(self):
        # Consume protocol framing only. Pixel payloads are discarded in chunks,
        # never decoded, saved, or inspected for message content.
        def read(size):
            out=bytearray()
            while len(out)<size and not self.stopping.is_set():
                try:
                    part=self.sock.recv(min(65536,size-len(out)))
                except socket.timeout:
                    continue
                if not part:
                    raise ConnectionError('VNC 输入连接已断开')
                out.extend(part)
            if len(out)!=size:
                raise ConnectionError('VNC 输入连接已关闭')
            return bytes(out)
        def discard(size):
            while size:
                count=min(size,65536)
                read(count)
                size-=count
        while not self.stopping.is_set():
            try:
                kind=read(1)[0]
                if kind==0:
                    count=struct.unpack('>H',read(3)[1:])[0]
                    for _ in range(count):
                        x,y,w,h,encoding=struct.unpack('>HHHHi',read(12))
                        if encoding==0:
                            discard(w*h*4)
                        elif encoding==-223:
                            self.width,self.height=w,h
                        elif encoding==-224:
                            break
                        else:
                            raise ValueError('VNC 输入通道收到不支持的帧编码')
                elif kind==3:
                    length=struct.unpack('>i',read(7)[3:])[0]
                    if abs(length)>4*1024*1024:
                        raise ValueError('VNC 剪贴板响应过长')
                    payload=read(abs(length))
                    if length<0 and len(payload)>=4 and struct.unpack('>I',payload[:4])[0] & (1<<24):
                        self.clipboard_ready.set()
                elif kind==2:
                    continue
                else:
                    raise ValueError('VNC 输入协议响应无法识别')
            except (OSError,ValueError) as exc:
                self.receive_error=exc
                self.clipboard_ready.set()
                break

    def pointer(self, x, y, pressed):
        self.sock.sendall(struct.pack('>BBHH', 5, bool(pressed),
            round(x * (self.width-1)), round(y * (self.height-1))))

    async def scroll(self, toward_top, small=False):
        start, end = (.36, .55 if small else .69) if toward_top else (.69, .50 if small else .36)
        try:
            for step in range(17):
                self.pointer(.5, start + (end-start)*step/16, True)
                await asyncio.sleep(.025)
        finally:
            with contextlib.suppress(OSError):
                self.pointer(.5, end, False)

    def key(self, code, down):
        self.sock.sendall(struct.pack('>BB2xI', 4, bool(down), code))

    def paste(self, text):
        from pymobiledevice3.remote.core_device import rfb_clipboard as clip
        self.clipboard_ready.clear()
        self.sock.sendall(struct.pack('>BBHi', 2, 0, 1, clip.ENC_EXTENDED_CLIPBOARD))
        if not self.clipboard_ready.wait(8) or self.receive_error:
            raise ValueError('手机剪贴板通道未就绪，请重连所选设备后重试')
        for msg in (clip.extended_caps(), clip.extended_provide(text)):
            self.sock.sendall(b'\x06' + msg[1:])
        time.sleep(0.8)
        try:
            self.key(0xffeb, True)
            self.key(ord('v'), True)
            self.key(ord('v'), False)
        finally:
            self.key(0xffeb, False)

    def home(self):
        self.sock.sendall(struct.pack('>BBHH', 5, 4, 0, 0))
        self.sock.sendall(struct.pack('>BBHH', 5, 0, 0, 0))

    def close(self):
        self.stopping.set()
        with contextlib.suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        self.sock.close()


def archive(device, current):
    from message_archive import archive_reading
    current.update(device=device, created=datetime.now().isoformat(), history_complete=False)
    current.setdefault('scope', '手机界面结构读取 · 当前可见气泡 · 非完整历史')
    path = DATA / 'diagnostics' / ('native-desktop-' + uuid.uuid4().hex + '.json')
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    result = archive_reading(path)
    return {'conversation_id': Path(result['output']).stem, 'message_count': len(current['messages']),
            'message': current['scope'], 'ui_start_confirmed': current.get('ui_start_confirmed', False),
            'ui_history_complete': current.get('ui_history_complete', False)}


async def capture_from_top(service, port):
    from native_ui_scan import scan
    from native_conversation import phone_key
    from sms_collect import parse_records, TIME
    from native_history_reader import collect_history
    contact_hint = None

    async def read_page():
        nonlocal contact_hint
        scanned = await scan(service, limit=3000, seconds=18, settle=0, start_from_last=False)
        if not scanned.complete:
            raise ValueError(f'界面遍历未完整确认（{scanned.reason}）')
        records = [{'caption': item.caption or '', 'platform_identifier': item.platform_identifier} for item in scanned]
        contact, messages, unknown = parse_records(records)
        actual_contact = contact
        if contact:
            contact_hint = contact
        elif contact_hint:
            # The identity hint only classifies rows after the same verified
            # header scrolls offscreen; it is never a new identity observation.
            _, messages, unknown = parse_records([{'caption': contact_hint+', Show Conversation Details, Button'}, *records])
        anchors = [r['caption'] for r in records if TIME.search(r['caption'])
                   or 'Includes picture' in r['caption']]
        loading_labels = {'loading', 'loading earlier messages', 'loading messages',
                          '加载中', '正在加载', '正在载入更早的信息'}
        loading = any(r['caption'].strip().lower() in loading_labels or
                      r['caption'].endswith((', Progress Indicator', ', Activity Indicator')) for r in records)
        return {'contact': actual_contact or contact_hint, 'phone_number': phone_key(actual_contact) if actual_contact else None,
                'messages': messages, 'unclassified': unknown, 'raw_elements': records,
                'bubble_anchors': anchors, 'loading': loading, 'scan_complete': True,
                'source': 'native-structure-history'}

    inp = Input(port)
    try:
        return await collect_history(read_page, inp.scroll)
    finally:
        inp.close()


async def phone_action(body):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
    from native_workspace import read, prepared_send_control, composer_is_empty
    device, action = body['device'], body['action']
    ld = await create_using_usbmux(serial=device, connection_type='USB',
        usbmux_address='127.0.0.1:27015', pairing_records_cache_folder=DATA, autopair=False)
    try:
        async with AccessibilityAudit(ld) as service:
            if action in ('capture','capture_visible'):
                from native_reverse_reader import capture_reverse
                return archive(device, await capture_reverse(service))
            current = await read(service)
            from send_policy import validate_send_text
            from message_archive import conversations
            conversation = next((c for c in conversations(device) if c['id'] == body.get('conversation_id')), None)
            if not conversation or current.get('phone_number') != conversation.get('phone_number'):
                raise ValueError('当前手机会话与所选记录号码不一致，请读取当前气泡后重试')
            text = validate_send_text(body.get('text', ''))
            if action == 'paste':
                captions = [r['caption'] for r in current['raw_elements']]
                if not composer_is_empty(captions):
                    raise ValueError('手机已有草稿，保留原内容；请先处理手机草稿')
                candidates = [r for r in current['raw_elements'] if r['caption'] in
                    ('Message', 'Message, iMessage', 'Message, Text Message', 'Message, Text Message, SMS')]
                if len(candidates) != 1:
                    raise ValueError('未定位到唯一原生输入框，请在手机点击输入框后重试')
                await service.perform_press(bytes.fromhex(candidates[0]['platform_identifier']))
                inp = Input(body['port'])
                try:
                    await asyncio.to_thread(inp.paste, text)
                finally:
                    inp.close()
                await asyncio.sleep(.5)
                prepared = await read(service)
                prepared_send_control(prepared, conversation['phone_number'], text)
                return {'message': '已核验正文填入手机，尚未发送'}
            if action != 'send' or body.get('confirm') is not True:
                raise ValueError('无效发送请求')
            button = prepared_send_control(current, conversation['phone_number'], text)
            token = body.get('token', '')
            if not token or any(c not in '0123456789abcdef' for c in token):
                raise ValueError('发送标识无效')
            path = DATA / 'workspace' / 'replies' / ('desktop-' + token + '.json')
            record = {'device': device, 'phone_number': conversation['phone_number'],
                      'text': text, 'status': 'send_requested', 'created': datetime.now().isoformat()}
            with path.open('x', encoding='utf-8') as output:
                json.dump(record, output, ensure_ascii=False)
            await service.perform_press(bytes.fromhex(button['platform_identifier']))
            await asyncio.sleep(1)
            after = await read(service)
            before_count = sum(m['side'] == 'outgoing' and m.get('text') == text for m in current['messages'])
            after_count = sum(m['side'] == 'outgoing' and m.get('text') == text for m in after['messages'])
            if after.get('phone_number') != conversation['phone_number'] or after_count <= before_count:
                raise ValueError('发送结果未确认，请查看手机；禁止自动重发')
            record['status'] = 'sent_verified'
            path.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
            return {**archive(device, after), 'message': '已核验手机新增发出的气泡'}
    finally:
        await ld.close()


async def run(body):
    action = body['action']
    if action in ('paste','send','home'):
        from native_device_control import permission
        state=permission(body['port'])
        if not state.get('enabled') or not state.get('control_enabled'):
            raise ValueError('该手机已断开或处于仅监看模式，请先允许操作')
    if action == 'prepare':
        from pairing_patch import install
        install()
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.mobile_image_mounter import MobileImageMounterService
        ld = await create_using_usbmux(serial=body['device'],connection_type='USB',autopair=False,
            pairing_records_cache_folder=DATA,usbmux_address='127.0.0.1:27015')
        try:
            if not ld.paired:
                raise ValueError('现有信任身份未通过，请解锁并重新建立信任')
            async with MobileImageMounterService(ld) as service:
                if not await service.query_developer_mode_status():
                    raise ValueError('请在手机设置开启开发者模式，重启后确认开启')
                if await service.copy_devices():
                    return {'ready':True,'message':'开发者镜像已挂载'}
        finally:
            await ld.close()
        env = os.environ.copy()
        env.update(PYMOBILEDEVICE3_UDID=body['device'],PYTHONUTF8='1')
        proc = await asyncio.create_subprocess_exec(sys.executable,str(DATA/'vnc_av_continuous.py'),
            '-v','mounter','auto-mount',env=env,stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,creationflags=0x08000000)
        try:
            out,err = await asyncio.wait_for(proc.communicate(),240)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise ValueError('开发者镜像准备超时，请检查 USB 与网络后重试')
        log = DATA/'logs'/('auto-prepare-'+body['device']+'.log')
        log.write_bytes(out+b'\n'+err)
        if proc.returncode:
            raise ValueError('开发者镜像准备失败，详情已保存到本地日志')
        return {'ready':True,'message':'开发者镜像已自动准备完成'}
    if action == 'paste':
        text = body.get('text','')
        if not isinstance(text,str) or not text.strip() or len(text)>32768:
            raise ValueError('请输入要粘贴的正文（最多 32768 字）')
        # Manual paste follows the selected phone's focused field, including
        # non-SMS inputs. It must not depend on a saved SMS history/recipient.
        inp = Input(body['port'])
        try:
            await asyncio.to_thread(inp.paste,text)
        finally:
            inp.close()
        return {'message':'已请求粘贴到所选手机当前输入框；未执行发送，请核对手机内容'}
    if action == 'trust':
        from pairing_patch import install
        install()
        from device_trust import repair
        return await repair(body['device'], DATA)
    if action == 'probe':
        from pairing_patch import install
        install()
        from pymobiledevice3.usbmux import list_devices
        from pymobiledevice3.lockdown import create_using_usbmux
        async def check(d):
            row = {'udid': d.serial, 'trusted': False}
            try:
                ld = await create_using_usbmux(serial=d.serial, autopair=False, connection_type='USB',
                    pairing_records_cache_folder=DATA, usbmux_address='127.0.0.1:27015')
                try:
                    row['trusted'] = bool(ld.paired)
                    row['name'] = (ld.all_values or {}).get('DeviceName', 'iPhone')
                finally:
                    await ld.close()
            except Exception as exc:
                row['error'] = str(exc)
            return row
        return {'devices': await asyncio.gather(*(check(d) for d in await list_devices()))}
    if action in ('capture', 'capture_visible', 'send'):
        return await phone_action(body)
    if action == 'home':
        inp = Input(body['port'])
        try:
            inp.home()
        finally:
            inp.close()
        return {'message': '已请求返回手机主页'}
    from message_archive import conversations
    saved = conversations(body['device'])
    if action == 'saved':
        return {'conversations': saved}
    conversation = next((c for c in saved if c['id'] == body.get('conversation_id')), None)
    if not conversation:
        raise ValueError('请选择已读取的会话')
    if action == 'history':
        from message_backup import refresh_snapshot, read_snapshot
        number = conversation.get('phone_number')
        if not number:
            raise ValueError('该会话尚未确认完整电话号码')
        await refresh_snapshot(DATA, body['device'])
        snapshot = read_snapshot(DATA, body['device'], number)
        if not snapshot:
            raise ValueError('备份中没有找到该号码的短信')
        current = {**conversation, **snapshot, 'source': 'backup-database', 'created': datetime.now().isoformat()}
        from message_archive import archive_reading
        path = DATA / 'diagnostics' / ('native-desktop-history-' + uuid.uuid4().hex + '.json')
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
        result = archive_reading(path)
        return {'conversation_id': Path(result['output']).stem, 'message_count': len(current['messages'])}
    from contact_profiles import read_profile, save_profile
    if action == 'profile':
        return read_profile(DATA, body['device'], conversation)
    if action == 'save_profile':
        return save_profile(DATA, body['device'], conversation, body['fields'])
    raise ValueError('未知操作')


if __name__ == '__main__':
    try:
        body = json.load(sys.stdin)
        value = asyncio.run(run(body))
        print(json.dumps(value, ensure_ascii=True), flush=True)
    except Exception as exc:
        print(json.dumps({'error': str(exc) or type(exc).__name__}, ensure_ascii=True), flush=True)
        sys.exit(1)
