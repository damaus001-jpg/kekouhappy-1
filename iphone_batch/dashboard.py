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
from concurrent.futures import ThreadPoolExecutor
import controller

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
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
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
    args=parser.parse_args()
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
    registry=DeviceRegistry(devices,args.base_port,args.port)
    manager=FocusManager(devices,token)
    children={}
    from viewer_retry import ViewerRetryPolicy
    retry_policy=ViewerRetryPolicy()
    generations={}
    from text_translation import TextTranslationService
    from translation_routes import dispatch
    from translation import TranslationError
    translation_service=TextTranslationService()
    from workspace_service import WorkspaceService
    workspace_service=WorkspaceService()
    stopping=threading.Event()
    health_pool=ThreadPoolExecutor(max_workers=8,thread_name_prefix='viewer-health')
    from notification_monitor import NotificationMonitor
    notification_monitor=NotificationMonitor(devices,workspace_service.phone_lock,
        manager.notification_lease,workspace_service.notifications,
        lambda d: viewer_ready(d),stopping,
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

    def launch_viewer(device):
        port=device['port']
        generations[device['udid']]=generations.get(device['udid'],0)+1
        env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','IPHONE_BATCH_CONTROL_TOKEN':token,'IPHONE_BATCH_TRANSLATION_URL':f'http://127.0.0.1:{args.port}/internal/translation'}
        logs=ROOT/'.device-data'/'diagnostics'
        logs.mkdir(parents=True,exist_ok=True)
        with (logs/f'dashboard-{port}.log').open('ab') as output:
            children[device['udid']]=subprocess.Popen(
                [sys.executable,str(ROOT/'controller.py'),'screen','--udid',device['udid'],'--port',str(port)],
                env=env,stdout=output,stderr=subprocess.STDOUT,
                creationflags=0x08000000 if os.name=='nt' else 0)

    def stop_viewer(device):
        import psutil
        child=children.pop(device['udid'],None)
        if child is None or child.poll() is not None:return
        try:
            process=psutil.Process(child.pid)
            command=process.cmdline()
            if str(ROOT/'controller.py') not in command or device['udid'] not in command:
                raise RuntimeError('设备进程身份变化，已取消停止')
            descendants=[p for p in process.children(recursive=True) if p.name().lower().startswith('python')]
            allowed={str(ROOT/'controller.py'),str(ROOT/'pmd_entry.py')}
            if any(not allowed.intersection(p.cmdline()) for p in descendants):
                raise RuntimeError('设备子进程身份变化，已取消停止')
            process.terminate()
            for descendant in reversed(descendants):
                try:descendant.terminate()
                except psutil.NoSuchProcess:pass
        except psutil.NoSuchProcess:pass

    def refresh_connected_devices():
        discovered=controller.discover()
        with registry.lock, workspace_service.phone_lock:
            with manager.lock:
                added,removed=registry.refresh(discovered)
                if manager.active not in {d['udid'] for d in devices}:manager.active=None
                if manager.selected not in {d['udid'] for d in devices}:manager.selected=None
            notification_monitor.update_devices(devices)
            for device in removed:stop_viewer(device)
            for device in devices:
                child=children.get(device['udid'])
                if child is not None and child.poll() is None:continue
                retry_policy.reset(device['udid'])
                try:launch_viewer(device)
                except OSError:device['error']='投屏启动失败，正在重试'
            return {'count':len(devices),'added':len(added),'removed':len(removed),'active':manager.active}

    def watch_viewers():
        while not stopping.wait(3):
          with registry.lock:
            for device in list(devices):
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
        child=children.get(device['udid'])
        if child is None or child.poll() is not None:return False
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{device['port']}/",timeout=0.5) as response:
                ready=response.status==200
                if ready and children.get(device['udid']) is child:retry_policy.reset(device['udid'])
                return ready
        except OSError:
            return False

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
                and self.headers.get('Sec-Fetch-Site')!='cross-site')

        def do_GET(self):
            if not self.allowed():
                return self.respond(403,{'error':'localhost only'})
            if self.path=='/':
                return self.respond(200,(ROOT/'web/workspace.html').read_bytes(),'text/html; charset=utf-8')
            assets = {'/dashboard.css': 'text/css; charset=utf-8', '/dashboard.js': 'text/javascript; charset=utf-8',
                      '/workspace.js': 'text/javascript; charset=utf-8', '/gpt_export.js': 'text/javascript; charset=utf-8', '/contact_profile.js': 'text/javascript; charset=utf-8', '/electric-doodles.svg':'image/svg+xml', '/brand-logo.jpg': 'image/jpeg'}
            if self.path in assets:
                path = ROOT/'web'/self.path.lstrip('/')
                if path.is_file():
                    return self.respond(200, path.read_bytes(), assets[self.path])
                return self.respond(404, {'error': 'asset not found'})
            parsed = urlsplit(self.path)
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
                rows.append({**device,'ready':ready,'active':manager.active==device['udid'],
                             'notifications':notifications})
            return self.respond(200,{'devices':rows,'active':manager.active,'selected':manager.selected,'scan_enabled':notification_monitor.enabled})

        def do_POST(self):
            if not self.allowed():
                return self.respond(403,{'error':'same-origin localhost access required'})
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
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=4096:raise ValueError('无效请求')
                    self.connection.settimeout(15)
                    body=json.loads(self.rfile.read(length))
                    if not isinstance(body,dict):raise ValueError('无效请求')
                    device=body.get('device')
                    if not isinstance(device,str) or device not in {d['udid'] for d in devices}:raise ValueError('请选择有效的手机')
                    result=workspace_service.retranslate_message(device,body.get('conversation_id'),body.get('message_index'),translation_service)
                    return self.respond(200,result)
                except (ValueError,TypeError,TranslationError) as exc:
                    return self.respond(400,{'error':str(exc)})
                except Exception:
                    return self.respond(500,{'error':'重新翻译失败，原译文已保留，请稍后重试'})
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
                if not hmac.compare_digest(self.headers.get('X-Control-Token',''),token):
                    return self.respond(403,{'error':'invalid control token'})
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=3*1024*1024:raise ValueError()
                    self.connection.settimeout(10)
                    body=json.loads(self.rfile.read(length))
                    device=body.get('device')
                    if device not in children:raise ValueError()
                    if body.get('action')!='status' and manager.active!=device:
                        return self.respond(200,{'error':'???????????'})
                    result=dispatch(translation_service,device,body)
                    return self.respond(200,result)
                except TranslationError as exc:
                    return self.respond(200,{'error':str(exc)})
                except Exception:
                    return self.respond(200,{'error':'????????????'})
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
                    manager.select(body['udid'],ready=viewer_ready(target))
                return self.respond(200,{'active':manager.active,'selected':manager.selected})
            except (ValueError, KeyError, TypeError):
                return self.respond(400,{'error':'invalid device selection'})
            except Exception:
                return self.respond(503,{'error':'设备切换未完成，请稍后重试','active':manager.active})

    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    try:
        for device in devices:
            launch_viewer(device)
        threading.Thread(target=watch_viewers,daemon=True).start()
        threading.Thread(target=notification_monitor.run,daemon=True).start()
        controller.emit({'status':'dashboard_ready','url':f'http://127.0.0.1:{args.port}/','devices':devices})
        server.serve_forever(poll_interval=0.25)
    finally:
        stopping.set()
        health_pool.shutdown(wait=False,cancel_futures=True)
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
