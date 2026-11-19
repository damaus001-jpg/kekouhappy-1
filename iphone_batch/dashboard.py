"""Run up to ten USB viewers with one active control and clipboard owner."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import hmac
import time
import urllib.request
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, wait
import controller
from workspace_access import AccessVerifier, HEADER, signed_opener
from cpu_metrics import create_cpu_reader

ROOT = Path(__file__).resolve().parent


def reveal_developer_mode(udid):
    if udid not in {row['udid'] for row in controller.discover()}:
        raise ValueError('手机已断开，请重新连接后重试')
    result = subprocess.run(
        controller.command_for(udid, ['amfi', 'reveal-developer-mode']),
        env=controller.device_environment(udid), capture_output=True, timeout=25,
        creationflags=0x08000000 if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError('显示入口失败，请解锁手机、确认信任此电脑后重试')
    return {'device': udid, 'message': '已请求显示入口。请重新打开手机“设置 → 隐私与安全性”，滑到最底部打开“开发者模式”，按提示重启并确认开启。'}


def play_notification_sound(device):
    """Play the Windows notification sound without browser autoplay restrictions."""
    if os.name=='nt':
        import winsound
        winsound.PlaySound('SystemNotification',winsound.SND_ALIAS | winsound.SND_ASYNC)


class CpuUsage:
    """Cache whole-computer load; HTTP threads never take blocking CPU samples."""
    def __init__(self, reader=None):
        self.sample = (None, 0)
        self.reader = reader

    def run(self, stopping):
        primed = False
        reader = self.reader
        try:
            while not stopping.is_set():
                try:
                    if reader is None:
                        reader = create_cpu_reader()
                    percent = reader()
                    # The first read only establishes this thread's baseline.
                    self.sample = (round(percent, 1), time.monotonic()) if primed else (None, 0)
                    primed = True
                except Exception:
                    self.sample = (None, 0)
                    primed = False
                stopping.wait(3)
        finally:
            close = getattr(reader, 'close', None)
            if close:
                close()

    def snapshot(self):
        percent, sampled_at = self.sample
        return percent if time.monotonic() - sampled_at <= 5 else None


class FocusManager:
    def __init__(self, devices, token, transport=None):
        self.devices = devices
        self.token = token
        self.active = None
        self.selected = None
        self.lock = threading.Lock()
        self.notification_users = {}
        self.transport = transport or self._transport

    def _transport(self, device, active):
        request = urllib.request.Request(f"http://127.0.0.1:{device['port']}/control-mode",
            data=json.dumps({'active':active}).encode(),
            headers={'Content-Type':'application/json', 'X-Control-Token':self.token}, method='POST')
        opener = signed_opener()
        with opener.open(request, timeout=5) as response:
            data=json.load(response)
        if data.get('active') is not active:
            raise RuntimeError('Device control state did not match requested state')

    def select(self, udid, *, ready=True):
        with self.lock:
            target = next((device for device in self.devices if device['udid']==udid),None)
            if target is None:
                raise ValueError('Unknown device')
            # All phones start read-only. Disable the previous owner before
            # enabling the next one; failed transitions leave no new owner.
            previous = self.active
            if previous == udid and ready:
                self.selected = udid
                return
            if previous is not None:
                old = next(device for device in self.devices if device['udid']==previous)
                if not self.notification_users.get(previous):
                    self.transport(old, False)
            self.active = None
            if not ready:
                # Selecting a USB phone for setup must not require a running viewer.
                self.selected = udid
                return
            try:
                if not self.notification_users.get(udid):
                    self.transport(target, True)
            except Exception:
                # If a reply was lost, revoke the possibly enabled target too.
                try:
                    self.transport(target, False)
                except Exception:
                    pass
                raise
            self.active = udid
            self.selected = udid

    @contextmanager
    def notification_lease(self, udid):
        """Grant background gestures independently for each device."""
        with self.lock:
            target=next((d for d in self.devices if d['udid']==udid),None)
            if target is None:raise ValueError('Unknown device')
            if not self.notification_users.get(udid) and self.active!=udid:
                try:self.transport(target,True)
                except Exception:
                    try:self.transport(target,False)
                    except Exception:pass
                    raise
            self.notification_users[udid]=self.notification_users.get(udid,0)+1
        try:
            yield
        finally:
            with self.lock:
                self.notification_users[udid]-=1
                if not self.notification_users[udid] and self.active!=udid:
                    self.transport(target,False)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--udid',action='append')
    parser.add_argument('--port',type=int,default=8070)
    parser.add_argument('--base-port',type=int,default=8080)
    parser.add_argument('--device-map',default=str(ROOT/'.device-data'/'workspace'/'device-map.json'))
    args=parser.parse_args()
    access=AccessVerifier()
    from device_policy import load_enabled, load_transport, load_readonly, save_access, connection_allowed, require_connection
    policy_path=ROOT/'.device-data'/'workspace'/'device-policy.json'
    enabled=load_enabled(policy_path)
    readonly=load_readonly(policy_path)
    load_transport(policy_path)
    def control_allowed(device):
        return connection_allowed(device, enabled) and device['udid'] not in readonly
    def require_control(device):
        require_connection(device, enabled)
        if device['udid'] in readonly:raise ValueError('该设备仅监看，请先允许操作')
    requested=args.udid or [row['udid'] for row in controller.discover()]
    udids=controller.resolve_devices(requested) if requested else []
    if not 1024 <= args.port <= 65535 or not 1024 <= args.base_port <= 65535-len(udids)+1:
        raise ValueError('Invalid ports')
    if args.port in range(args.base_port,args.base_port+len(udids)):
        raise ValueError('Dashboard and device ports must be different')
    token=secrets.token_urlsafe(32)
    devices=[{'udid':udid,'name':f'iPhone {index+1}', 'port':args.base_port+index}
             for index,udid in enumerate(udids)]
    from device_registry import DeviceRegistry
    registry=DeviceRegistry(devices,args.base_port,args.port,state_path=args.device_map)
    manager=FocusManager(devices,token)
    original_transport=manager.transport
    def guarded_transport(device, active):
        if active:require_control(device)
        return original_transport(device, active)
    manager.transport=guarded_transport
    children={}
    from viewer_retry import ViewerRetryPolicy
    retry_policy=ViewerRetryPolicy()
    generations={}
    from translation import TranslationError
    from workspace_service import WorkspaceService
    workspace_service=WorkspaceService()
    stopping=threading.Event()
    health_pool=ThreadPoolExecutor(max_workers=8,thread_name_prefix='viewer-health')
    input_readiness_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='input-readiness')
    input_readiness_lock=threading.Lock()
    input_readiness={}
    trust_pending=set()
    trust_lock=threading.Lock()
    from notification_monitor import NotificationMonitor
    from device_reconnect import DeviceReconnects, reset_phone_session, repair_phone_trust
    notification_monitor=NotificationMonitor(devices,workspace_service.phone_lock,
        manager.notification_lease,workspace_service.notifications,
        lambda d: control_allowed(d) and not reconnects.pending(d['udid']) and viewer_ready(d),stopping,
        lock_for=workspace_service.device_lock,manual_device=lambda: manager.active,
        on_new_cards=play_notification_sound)
    scan_policy_path=ROOT/'.device-data'/'workspace'/'scan-policy.json'
    scan_policy_lock=threading.Lock()
    try:
        scan_enabled=json.loads(scan_policy_path.read_text(encoding='utf-8')).get('enabled',True)
        if not isinstance(scan_enabled,bool):scan_enabled=True
    except (OSError,ValueError,AttributeError):scan_enabled=True
    workspace_service.notification_runner.set_enabled(scan_enabled)
    notification_monitor.set_enabled(scan_enabled)

    def set_scan_enabled(enabled):
        with scan_policy_lock:
            workspace_service.write(scan_policy_path,{'enabled':enabled})
            if enabled:
                workspace_service.notification_runner.set_enabled(True)
                notification_monitor.set_enabled(True)
                cancelled=0
            else:
                notification_monitor.set_enabled(False)
                cancelled=workspace_service.notification_runner.set_enabled(False)
            return {'enabled':notification_monitor.enabled,'cancelled':cancelled}

    def start_viewer_now(device):
        if not connection_allowed(device, enabled):
            device['error']='已停用，未建立连接'
            return
        port=device['port']
        generations[device['udid']]=generations.get(device['udid'],0)+1
        with input_readiness_lock:
            input_readiness.pop(device['udid'],None)
        env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','IPHONE_BATCH_CONTROL_TOKEN':token,'IPHONE_BATCH_TRANSLATION_URL':f'http://127.0.0.1:{args.port}/internal/translation'}
        logs=ROOT/'.device-data'/'diagnostics'
        logs.mkdir(parents=True,exist_ok=True)
        with (logs/f'dashboard-{port}.log').open('ab') as output:
            children[device['udid']]=subprocess.Popen(
                [sys.executable,str(ROOT/'controller.py'),'screen','--udid',device['udid'],'--port',str(port)],
                env=env,stdout=output,stderr=subprocess.STDOUT,
                creationflags=0x08000000 if os.name=='nt' else 0)

    def launch_viewer(device):
        if not connection_allowed(device,enabled):
            device['error']='已手动断开，画面与操作均已关闭'
            return
        if startup_queue.request(device):device['error']='排队等待接入，逐台准备画面…'

    def stop_viewer(device):
        child=children.get(device['udid'])
        if child is None or child.poll() is not None:return
        from owned_viewer_process import stop_tree
        stop_tree(child.pid,ROOT/'controller.py',device['udid'])
        if children.get(device['udid']) is child:children.pop(device['udid'],None)

    def change_device_access(device, changes):
        nonlocal enabled, readonly
        with registry.lock:
            if device not in devices:raise ValueError('该手机已断开，请刷新设备列表')
            if reconnects.pending(device['udid']) or device['udid'] in trust_pending:
                raise ValueError('该手机正在连接或确认信任，请稍后操作')
            if not workspace_service.phone_lock.acquire(blocking=False):
                raise ValueError('手机任务正在执行，完成后再切换，草稿保持不变')
            lock=workspace_service.device_lock(device['udid'])
            acquired=False
            try:
                acquired=lock.acquire(blocking=False)
                if not acquired:raise ValueError('该手机正在处理任务，请稍后再切换')
                next_enabled=set(enabled if enabled is not None else registry.known)
                next_readonly=set(readonly)
                target=device['udid']
                if 'enabled' in changes:
                    if changes['enabled']:next_enabled.add(target)
                    else:next_enabled.discard(target)
                if 'readonly' in changes:
                    if changes['readonly']:next_readonly.add(target)
                    else:next_readonly.discard(target)
                save_access(policy_path, next_enabled, next_readonly)
                enabled,readonly=frozenset(next_enabled),frozenset(next_readonly)
                generations[target]=generations.get(target,0)+1
                with input_readiness_lock:input_readiness.pop(target,None)
                if not control_allowed(device):
                    with manager.lock:
                        if manager.active==target:
                            try:manager.transport(device,False)
                            except Exception:stop_viewer(device)
                            manager.active=None
                if not connection_allowed(device, enabled):
                    startup_queue.cancel(target)
                    stop_viewer(device)
                    retry_policy.reset(target)
                    device['error']='已手动断开，画面与操作均已关闭'
                    message='已断开此台，停止画面、解码和操作；不会自动重连'
                else:
                    child=children.get(target)
                    if child is None or child.poll() is not None:
                        retry_policy.reset(target)
                        device['error']='正在接入此台…'
                        launch_viewer(device)
                        message='已请求接入此台，正在准备画面'
                    else:
                        message='仅监看，鼠标、键盘、粘贴和手机操作已锁定' if target in readonly else '已允许操作'
                        if manager.selected==target and control_allowed(device):manager.select(target,ready=True)
                return {'ok':True,'enabled':connection_allowed(device,enabled),
                        'readonly':target in readonly,'message':message}
            finally:
                if acquired:lock.release()
                workspace_service.phone_lock.release()

    def refresh_connected_devices():
        discovered=controller.discover()
        with registry.lock, workspace_service.phone_lock:
            with manager.lock:
                added,removed=registry.refresh(discovered)
                if manager.active not in {d['udid'] for d in devices}:manager.active=None
                if manager.selected not in {d['udid'] for d in devices}:manager.selected=None
            notification_monitor.update_devices(devices)
            for device in removed:
                startup_queue.cancel(device['udid'])
                stop_viewer(device)
            for device in devices:
                if device['udid'] in trust_pending or reconnects.pending(device['udid']) or startup_queue.pending(device['udid']):continue
                child=children.get(device['udid'])
                if child is not None and child.poll() is None:continue
                with input_readiness_lock:
                    input_readiness.pop(device['udid'],None)
                retry_policy.reset(device['udid'])
                try:launch_viewer(device)
                except OSError:device['error']='投屏启动失败，正在重试'
            return {'count':len(devices),'added':len(added),'removed':len(removed),'active':manager.active}

    def watch_viewers():
        while not stopping.wait(3):
          with registry.lock:
            for device in list(devices):
                if not connection_allowed(device, enabled):continue
                if startup_queue.pending(device['udid']):continue
                if startup_queue.terminal_failure(device['udid']):continue
                if device['udid'] in trust_pending or reconnects.pending(device['udid']):continue
                child=children.get(device['udid'])
                if child is not None and child.poll() is None:
                    continue
                with manager.lock:
                    if manager.active==device['udid']:
                        manager.active=None
                now=time.monotonic()
                last_error=None
                try:
                    path=ROOT/'.device-data'/'diagnostics'/f"dashboard-{device['port']}.log"
                    with path.open('rb') as log:
                        log.seek(max(0,path.stat().st_size-4096))
                        line=log.read().splitlines()[-1]
                        try:text=line.decode('utf-8')
                        except UnicodeDecodeError:text=line.decode('gb18030',errors='replace')
                        row=json.loads(text)
                        if row.get('status')=='error':last_error=str(row.get('message',''))[:240]
                except (OSError,ValueError,IndexError):
                    pass
                allowed=retry_policy.should_retry(device['udid'],generations.get(device['udid'],0),last_error,now)
                if not allowed:
                    device['error']=last_error or '投屏连接中断，稍后重试；也可点击设备列表刷新'
                    if retry_policy.requires_refresh(device['udid']):
                        device['error']+='；处理后点击设备列表刷新重试'
                    continue
                device['error']=last_error or '投屏进程退出，正在恢复；恢复后请重新选择手机'
                if stopping.is_set():
                    return
                try:launch_viewer(device)
                except OSError:device['error']='投屏启动失败，正在重试'

    def viewer_ready(device):
        return viewer_video_ready(device)

    def viewer_video_ready(device):
        """A device is connected only after it supplies a decodable video config."""
        if not connection_allowed(device, enabled):return False
        child=children.get(device['udid'])
        if child is None or child.poll() is not None:return False
        try:
            opener=signed_opener()
            with opener.open(f"http://127.0.0.1:{device['port']}/codec",timeout=1) as response:
                info=json.load(response)
            ready=bool(info.get('codec') and info.get('description'))
            if ready and children.get(device['udid']) is child:retry_policy.reset(device['udid'])
            return ready
        except (OSError,ValueError,TypeError):
            return False

    def record_input_readiness(udid, future, generation=None):
        if generation is not None and generation!=generations.get(udid,0):return
        if not control_allowed({'udid':udid}):return
        now=time.monotonic()
        try:
            result=future.result()
        except Exception:
            result={'ok':False,'state':'unavailable'}
        with input_readiness_lock:
            if generation is not None and generation!=generations.get(udid,0):return
            if not control_allowed({'udid':udid}):return
            previous=input_readiness.get(udid,{})
            if result.get('state')=='busy':
                last_success=previous.get('last_success',0)
                ready=bool(last_success and now-last_success<30)
            else:
                ready=result.get('ok') is True and result.get('state')=='ready'
                last_success=now if ready else 0
            input_readiness[udid]={
                'ready':ready,'state':result.get('state','unavailable'),
                'checked_at':now,'last_success':last_success,
                'probe':result.get('probe')}

    def probe_input_readiness(device):
        require_control(device)
        request=urllib.request.Request(
            f"http://127.0.0.1:{device['port']}/input-readiness", data=b'{}',
            headers={'Content-Type':'application/json','X-Control-Token':token}, method='POST')
        opener=signed_opener()
        with opener.open(request,timeout=6) as response:
            return json.load(response)

    def input_readiness_snapshot(udid):
        now=time.monotonic()
        with input_readiness_lock:
            value=dict(input_readiness.get(udid,{ }))
        last_success=value.get('last_success',0)
        ready=bool(value.get('ready') and last_success and now-last_success<30)
        return {'control_ready':ready,
                'control_state':value.get('state','unknown') if ready else ('stale' if last_success else value.get('state','unknown')),
                'control_checked_age':round(now-value['checked_at'],1) if value.get('checked_at') else None}

    def watch_input_readiness():
        # Probe in small batches so a 15-phone hub is not hit with 15 new HID
        # handshakes at once. Idle-state reports contain no pressed keys/touches.
        while not stopping.is_set():
            current=[device for device in devices if control_allowed(device) and device['udid'] not in trust_pending and not reconnects.pending(device['udid']) and children.get(device['udid']) is not None and children[device['udid']].poll() is None]
            for offset in range(0,len(current),4):
                if stopping.is_set():return
                batch=current[offset:offset+4]
                futures=[]
                for device in batch:
                    future=input_readiness_pool.submit(probe_input_readiness,device)
                    future.add_done_callback(lambda result, device=device, generation=generations.get(device['udid'],0): record_input_readiness(device['udid'],result,generation))
                    futures.append(future)
                wait(futures,timeout=7)
            stopping.wait(3)

    def rebuild_device(device):
        require_connection(device, enabled)
        lock=workspace_service.device_lock(device['udid'])
        acquired=False
        try:
            with registry.lock:
                if device not in devices:raise ValueError('手机已断开，请重新接入后刷新')
                if device['udid'] in trust_pending:raise ValueError('该手机正在等待信任确认')
                if not workspace_service.phone_lock.acquire(blocking=False):
                    raise ValueError('手机任务正在执行，请完成后再重新连接')
                try:
                    acquired=lock.acquire(blocking=False)
                    if not acquired:raise ValueError('该手机正在处理任务，请稍后重试')
                    with manager.lock:
                        startup_queue.cancel(device['udid'])
                        stop_viewer(device)
                        if manager.active==device['udid']:manager.active=None
                    with input_readiness_lock:input_readiness.pop(device['udid'],None)
                finally:workspace_service.phone_lock.release()
            # Only this explicit reconnect repairs trust. Keep the target's
            # lock while other phones remain usable during confirmation.
            reconnects.stage(device['udid'],'trusting')
            device['error']='正在检查并修复信任连接；若手机弹出提示，请确认信任'
            repair_phone_trust(device,stopping=stopping)
            if stopping.is_set():raise ValueError('工作台正在关闭，设备恢复已停止')
            reconnects.stage(device['udid'],'resetting')
            device['error']='正在清理手机端远程会话…'
            reset_error=None
            try:
                reset_phone_session(device,stopping=stopping)
            except Exception as error:
                # The cleanup command can fail on a stale USB tunnel even when
                # a fresh viewer session can still be established. Preserve
                # the failure for diagnostics, then make that bounded attempt.
                reset_error=str(error)[:320]
            with registry.lock:
                if device not in devices:raise ValueError('手机已断开，请重新接入后刷新')
                if stopping.is_set():raise ValueError('工作台正在关闭，设备恢复已停止')
                reconnects.stage(device['udid'],'starting')
                device['error']=('会话清理未确认，正在直接重建投屏：'+reset_error
                    if reset_error else '正在重建画面与操控连接…')
                retry_policy.reset(device['udid'])
                launch_viewer(device)
        except Exception as error:
            device['error']=str(error) if isinstance(error,(ValueError,RuntimeError)) else '重新连接未完成，请检查手机状态后重试'
            raise
        finally:
            if acquired:lock.release()

    def finish_reconnect(device):
        reconnects.stage(device['udid'],'checking')
        with registry.lock:
            if device not in devices:raise ValueError('手机已断开，请重新接入后刷新')
            if not workspace_service.phone_lock.acquire(blocking=False):return False
            try:
                # A user may have switched to another phone while this one
                # reconnects. Never steal that phone's control ownership.
                if manager.selected==device['udid']:manager.select(device['udid'],ready=True)
            finally:workspace_service.phone_lock.release()
        future=input_readiness_pool.submit(probe_input_readiness,device)
        record_input_readiness(device['udid'],future)
        if not input_readiness_snapshot(device['udid'])['control_ready']:
            raise ValueError('画面已恢复，但操控检查未通过，请检查手机或重试重新连接')
        device.pop('error',None)
        return True

    reconnects=DeviceReconnects(rebuild_device,viewer_video_ready,finish_reconnect,stopping,
        queued=lambda device:startup_queue.pending(device['udid']))

    cpu_usage = CpuUsage()
    from foreground_reader import ForegroundReader
    foreground_reader = ForegroundReader(workspace_service, lambda udid:
        manager.active == udid and manager.selected == udid
        and any(d['udid'] == udid and control_allowed(d) for d in devices)
        and not reconnects.pending(udid))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*unused):
            pass

        def respond(self, code, data, content_type='application/json; charset=utf-8'):
            body=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            host=self.headers.get('Host','')
            return (self.client_address[0]=='127.0.0.1'
                and host==f'127.0.0.1:{args.port}'
                and self.headers.get('Origin') in (None,'http://'+host)
                and self.headers.get('Sec-Fetch-Site')!='cross-site'
                and access.verify(self.command,args.port,self.path,self.headers.get(HEADER)))

        def do_GET(self):
            if not self.allowed():
                return self.respond(403,{'error':'请从授权客户端打开短信工作台'})
            if self.path=='/':
                return self.respond(200,(ROOT/'web/workspace.html').read_bytes(),'text/html; charset=utf-8')
            assets = {'/dashboard.css': 'text/css; charset=utf-8', '/dashboard.js': 'text/javascript; charset=utf-8',
                      '/foreground.js': 'text/javascript; charset=utf-8',
                      '/workspace.js': 'text/javascript; charset=utf-8', '/gpt_export.js': 'text/javascript; charset=utf-8', '/contact_profile.js': 'text/javascript; charset=utf-8', '/electric-doodles.svg':'image/svg+xml', '/brand-logo.jpg': 'image/jpeg'}
            if self.path in assets:
                path = ROOT/'web'/self.path.lstrip('/')
                if path.is_file():
                    return self.respond(200, path.read_bytes(), assets[self.path])
                return self.respond(404, {'error': 'asset not found'})
            parsed = urlsplit(self.path)
            if parsed.path == '/api/cpu':
                return self.respond(200, {'cpu_percent': cpu_usage.snapshot()})
            if parsed.path == '/api/contact-profile':
                query = parse_qs(parsed.query)
                device = query.get('device', [''])[0]
                if device not in {d['udid'] for d in devices}:
                    return self.respond(400, {'error':'请选择有效的手机'})
                try:
                    return self.respond(200,workspace_service.contact_profile(device,query.get('conversation',[''])[0]))
                except (ValueError,KeyError,OSError,TypeError):
                    return self.respond(400,{'error':'联系人资料读取失败，请刷新记录后重试'})
            if parsed.path == '/api/messages':
                device = parse_qs(parsed.query).get('device', [''])[0]
                if device not in {d['udid'] for d in devices}:
                    return self.respond(400, {'error': '请选择有效的手机'})
                from message_archive import conversations
                return self.respond(200, {'device': device, 'conversations': conversations(device)})
            if self.path!='/api/state':
                return self.respond(404,{'error':'not found'})
            rows=[]
            current_devices=list(devices)
            readiness=list(health_pool.map(viewer_ready,current_devices))
            for device,ready in zip(current_devices,readiness):
                try:notifications=notification_monitor.snapshot(device['udid'])
                except KeyError:notifications={'state':'waiting','items':[],'card_count':0}
                if ready:
                    device.pop('error',None)
                if not connection_allowed(device, enabled):
                    device['error']='已手动断开，画面与操作均已关闭'
                rows.append({**device,'ready':ready and not reconnects.pending(device['udid']),'active':manager.active==device['udid'],
                             'enabled':connection_allowed(device, enabled),
                             'readonly':device['udid'] in readonly,
                             **reconnects.snapshot(device['udid']),
                             **input_readiness_snapshot(device['udid']), 'trust_pending':device['udid'] in trust_pending,
                             'notifications':notifications})
            return self.respond(200,{'devices':rows,'active':manager.active,'selected':manager.selected,'scan_enabled':notification_monitor.enabled,'translation_enabled':False,'cpu_percent':cpu_usage.snapshot()})

        def do_POST(self):
            if not self.allowed():
                return self.respond(403,{'error':'请从授权客户端打开短信工作台'})
            if self.path == '/api/foreground':
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 4096:
                        raise ValueError('自动读取请求无效')
                    self.connection.settimeout(15)
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError('自动读取请求无效')
                    if body.get('action') == 'cancel':
                        return self.respond(200, foreground_reader.cancel(body))
                    if body.get('action') == 'release':
                        return self.respond(200, foreground_reader.release(body))
                    device = next((d for d in devices if d['udid'] == body.get('device')), None)
                    action = body.get('action')
                    if action not in ('prepare', 'probe', 'tick', 'sent_tail') or device is None:
                        raise ValueError('自动读取设备无效')
                    require_control(device)
                    if action == 'prepare':
                        result = foreground_reader.prepare(body, device['udid'])
                    elif action == 'probe':
                        result = foreground_reader.probe(body, device['udid'], f"http://127.0.0.1:{device['port']}")
                    elif action == 'sent_tail':
                        result = foreground_reader.verify_sent(body, device['udid'], f"http://127.0.0.1:{device['port']}")
                    else:
                        result = foreground_reader.tick(body, device['udid'], f"http://127.0.0.1:{device['port']}")
                    return self.respond(200, result)
                except (ValueError, TypeError, KeyError) as error:
                    return self.respond(400, {'error': str(error)})
            if self.path=='/api/devices/access':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024:raise ValueError('无效请求')
                    self.connection.settimeout(15)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict) or set(body)-{'device','enabled','readonly'}:raise ValueError('无效请求')
                    changes={key:body[key] for key in ('enabled','readonly') if key in body}
                    if not changes or any(type(value) is not bool for value in changes.values()):raise ValueError('开关状态无效')
                    device=next((d for d in devices if d['udid']==body.get('device')),None)
                    if device is None:raise ValueError('请选择已连接 USB 的手机')
                    return self.respond(200,change_device_access(device,changes))
                except (ValueError,TypeError) as error:return self.respond(400,{'error':str(error)})
                except Exception:return self.respond(503,{'error':'设备开关未完成，请检查状态；没有发送短信'})
            if self.path=='/api/notification-scan':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024:raise ValueError('无效请求')
                    self.connection.settimeout(10)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict) or not isinstance(body.get('enabled'),bool):raise ValueError('无效的遍历开关状态')
                    return self.respond(200,set_scan_enabled(body['enabled']))
                except (ValueError,TypeError) as exc:
                    return self.respond(400,{'error':str(exc)})
                except Exception:
                    return self.respond(503,{'error':'遍历开关未完成，请刷新状态后重试'})
            if self.path=='/api/devices/reconnect':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024:raise ValueError('无效请求')
                    self.connection.settimeout(10)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict):raise ValueError('无效请求')
                    device=next((d for d in devices if d['udid']==body.get('device')),None)
                    if device is None:raise ValueError('请选择已连接的手机')
                    require_connection(device, enabled)
                    if device['udid'] in trust_pending:raise ValueError('该手机正在等待信任确认')
                    identifier=reconnects.begin(device)
                    return self.respond(202,{'ok':True,'job':identifier,'message':'正在重新连接此设备，请稍候'})
                except (ValueError,TypeError) as exc:return self.respond(400,{'error':str(exc)})
            if self.path=='/api/devices/trust':
                device=None
                acquired=False
                lock=None
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024:raise ValueError('无效请求')
                    self.connection.settimeout(100)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict):raise ValueError('无效请求')
                    device=next((d for d in devices if d['udid']==body.get('device')),None)
                    if device is None:raise ValueError('请选择已连接的手机')
                    require_control(device)
                    if reconnects.pending(device['udid']):raise ValueError('该手机正在重新连接，请稍候')
                    if viewer_ready(device):raise ValueError('手机投屏已就绪，无需重新建立信任')
                    lock=workspace_service.device_lock(device['udid'])
                    acquired=lock.acquire(blocking=False)
                    if not acquired:raise ValueError('该手机正在处理其他任务，请稍后重试')
                    with trust_lock:
                        if device['udid'] in trust_pending:raise ValueError('该手机正在等待信任确认')
                        trust_pending.add(device['udid'])
                    device['error']='正在检查并修复信任连接；若手机弹出提示，请确认信任'
                    with manager.lock:
                        if manager.active==device['udid']:manager.active=None
                    stop_viewer(device)
                    result=repair_phone_trust(device,stopping=stopping)
                    with registry.lock:
                        if device['udid'] not in {d['udid'] for d in devices}:raise ValueError('信任已建立，但手机已断开，请重新连接')
                        retry_policy.reset(device['udid'])
                        device['error']='信任已建立，正在检查开发者模式并启动投屏…'
                        launch_viewer(device)
                    return self.respond(200,{'ok':True,'message':result['message']+'；正在检查开发者模式并启动投屏'})
                except subprocess.TimeoutExpired:
                    if device:device['error']='信任确认超时，请解锁手机后重试'
                    return self.respond(504,{'error':'信任确认超时，请解锁手机后重试'})
                except (ValueError,TypeError) as exc:
                    if device and acquired:device['error']=str(exc)
                    return self.respond(400,{'error':str(exc)})
                except Exception:
                    return self.respond(503,{'error':'建立信任未完成，请检查手机连接后重试'})
                finally:
                    if acquired:
                        with trust_lock:trust_pending.discard(device['udid'])
                        lock.release()
            if self.path=='/api/devices/refresh':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024:raise ValueError('无效请求')
                    self.connection.settimeout(10)
                    if not isinstance(json.loads(self.rfile.read(length)),dict):raise ValueError('无效请求')
                    return self.respond(200,refresh_connected_devices())
                except (ValueError,TypeError) as exc:
                    return self.respond(400,{'error':str(exc)})
                except Exception:
                    return self.respond(503,{'error':'USB 设备刷新未完成，请稍后重试'})
            if self.path=='/api/message-translation':
                return self.respond(410,{'error':'8070 已移除翻译功能'})
            if self.path=='/api/developer-mode/reveal':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=1024:raise ValueError('无效请求')
                    self.connection.settimeout(10)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict):raise ValueError('无效请求')
                    udid=body.get('device')
                    with workspace_service.phone_lock:
                        if not isinstance(udid,str) or udid not in {d['udid'] for d in devices} or manager.selected!=udid:
                            raise ValueError('请先选中要操作的手机')
                        require_control({'udid':udid})
                        with workspace_service.device_lock(udid):
                            result=reveal_developer_mode(udid)
                    return self.respond(200,result)
                except (ValueError,TypeError) as exc:
                    return self.respond(400,{'error':str(exc)})
                except subprocess.TimeoutExpired:
                    return self.respond(504,{'error':'显示入口超时，请检查手机解锁与连接状态后重试'})
                except Exception:
                    return self.respond(503,{'error':'无法连接手机，请解锁并确认信任此电脑后重试'})
            if self.path=='/api/contact-profile':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=128*1024:raise ValueError('联系人资料过长')
                    self.connection.settimeout(15)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict) or not isinstance(body.get('fields'),dict):raise ValueError('联系人资料格式无效')
                    if body.get('device') not in {d['udid'] for d in devices}:raise ValueError('请选择有效的手机')
                    return self.respond(200,workspace_service.contact_profile(body['device'],body.get('conversation'),body['fields']))
                except (ValueError,TypeError,KeyError,OSError) as exc:
                    return self.respond(400,{'error':'联系人资料保存失败，请检查内容或刷新后重试'})
            if self.path=='/api/gpt-summary':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=4*1024*1024:raise ValueError('汇总内容为空或过长')
                    self.connection.settimeout(15)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict):raise ValueError('汇总请求无效')
                    from gpt_bridge import open_gpt_draft
                    return self.respond(200,open_gpt_draft(body.get('text')))
                except (ValueError,TypeError) as exc:
                    return self.respond(400,{'error':str(exc)})
                except Exception:
                    return self.respond(500,{'error':'复制或打开 ChatGPT 失败，请重试；没有发送任何内容'})
            if self.path=='/api/notification-policy':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<4096:raise ValueError('无效请求')
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body.get('protected'),bool):raise ValueError('无效草稿状态')
                    notification_monitor.protect(body['device'],body['protected'])
                    return self.respond(200,{'ok':True})
                except (ValueError,KeyError,TypeError) as exc:
                    return self.respond(400,{'error':str(exc)})
            if self.path=='/api/workspace':
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=32768: raise ValueError('请求过大')
                    self.connection.settimeout(15)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict): raise ValueError('请求格式无效')
                    device=next((d for d in devices if d['udid']==body.get('device')),None)
                    with workspace_service.phone_lock:
                        if device is None or manager.active!=device['udid']: raise ValueError('请先选中要操作的手机')
                        require_control(device)
                        if reconnects.pending(device['udid']):raise ValueError('该手机正在重新连接，请稍候')
                        with workspace_service.device_lock(device['udid']):
                            result=workspace_service.dispatch(device['udid'],body,f"http://127.0.0.1:{device['port']}")
                        if body.get('action')=='notifications':
                            notification_monitor.record(device['udid'],result)
                        if body.get('action')=='open_notification':
                            notification_monitor.acknowledge(device['udid'],body['notification_id'])
                    return self.respond(200,result)
                except (ValueError, TranslationError) as exc:
                    return self.respond(400,{'error':str(exc)})
                except subprocess.TimeoutExpired:
                    return self.respond(504,{'error':'手机操作超时，请核对手机状态，不自动重试发送'})
                except Exception:
                    return self.respond(500,{'error':'工作台操作失败，请刷新记录；发送结果不明时请先核对手机'})
            if self.path=='/internal/translation':
                return self.respond(410,{'error':'8070 已移除翻译功能','disabled':True})
            if self.path!='/api/select':
                return self.respond(404,{'error':'not found'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 1024:
                    raise ValueError('Invalid request size')
                body=json.loads(self.rfile.read(length))
                with workspace_service.phone_lock:
                    target=next((d for d in devices if d['udid']==body['udid']),None)
                    if target is None:raise ValueError('Unknown device')
                    if reconnects.pending(target['udid']):raise ValueError('该手机正在重新连接，请稍候')
                    if target['udid'] in trust_pending:raise ValueError('该手机正在等待信任确认')
                    manager.select(body['udid'],ready=control_allowed(target) and viewer_ready(target))
                    readiness=input_readiness_snapshot(body['udid'])
                return self.respond(200,{'active':manager.active,'selected':manager.selected,**readiness})
            except (ValueError, KeyError, TypeError):
                return self.respond(400,{'error':'invalid device selection'})
            except Exception:
                return self.respond(503,{'error':'设备切换未完成，请稍后重试','active':manager.active})

    from viewer_start_queue import ViewerStartQueue
    import psutil
    def queued_start(device,ticket):
        with registry.lock:
            if device not in devices or not startup_queue.valid(device['udid'],ticket) or not connection_allowed(device,enabled):return False
            start_viewer_now(device)
            return True
    def startup_failed(device,error,ticket):
        with registry.lock:
            if not startup_queue.valid(device['udid'],ticket) or not connection_allowed(device,enabled):return
            stop_viewer(device)
            if (startup_queue.attempt(device['udid']) or 0)>0:
                device['error']='请重启手机'
            elif isinstance(error,TimeoutError) and '连接超过60秒' in str(error):
                device['error']='连接超过60秒，已跳过；30秒后重试一次'
            else:
                device['error']='本次连接失败，已跳过；30秒后重试一次'
    def startup_ready(device):
        if not viewer_video_ready(device):
            child=children.get(device['udid'])
            if child is not None and child.poll() is not None:raise RuntimeError('该台接入进程已退出')
            return False
        return True
    startup_queue=ViewerStartQueue(queued_start,startup_ready,
        lambda device:connection_allowed(device,enabled),startup_failed,stopping,
        busy=lambda:psutil.cpu_percent(interval=.2)>75)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    cpu_thread=threading.Thread(target=cpu_usage.run,args=(stopping,),name='system-cpu',daemon=True)
    try:
        cpu_thread.start()
        for device in devices:
            launch_viewer(device)
        threading.Thread(target=watch_viewers,daemon=True).start()
        threading.Thread(target=watch_input_readiness,daemon=True).start()
        threading.Thread(target=notification_monitor.run,daemon=True).start()
        controller.emit({'status':'dashboard_ready','url':f'http://127.0.0.1:{args.port}/','devices':devices})
        server.serve_forever(poll_interval=0.25)
    finally:
        stopping.set()
        foreground_reader.close()
        if cpu_thread.is_alive():cpu_thread.join(timeout=2)
        startup_queue.close()
        health_pool.shutdown(wait=False,cancel_futures=True)
        input_readiness_pool.shutdown(wait=False,cancel_futures=True)
        server.server_close()
        # Stop children and their upstream viewers even when the parent exits.
        import psutil
        for child in list(children.values()):
            try:
                process=psutil.Process(child.pid)
                descendants=process.children(recursive=True)
                for descendant in reversed(descendants):
                    descendant.terminate()
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)
            except (psutil.NoSuchProcess,subprocess.TimeoutExpired):
                pass


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
