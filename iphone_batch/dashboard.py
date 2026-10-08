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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import controller

ROOT = Path(__file__).resolve().parent


class FocusManager:
    def __init__(self, devices, token, transport=None):
        self.devices = devices
        self.token = token
        self.active = None
        self.lock = threading.Lock()
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

    def select(self, udid):
        with self.lock:
            target = next((device for device in self.devices if device['udid']==udid),None)
            if target is None:
                raise ValueError('Unknown device')
            # All phones start read-only. Disable the previous owner before
            # enabling the next one; failed transitions leave no new owner.
            previous = self.active
            if previous == udid:
                return
            if previous is not None:
                old = next(device for device in self.devices if device['udid']==previous)
                self.transport(old, False)
            self.active = None
            try:
                self.transport(target, True)
            except Exception:
                # If a reply was lost, revoke the possibly enabled target too.
                try:
                    self.transport(target, False)
                except Exception:
                    pass
                raise
            self.active = udid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--udid',action='append')
    parser.add_argument('--port',type=int,default=8070)
    parser.add_argument('--base-port',type=int,default=8080)
    args=parser.parse_args()
    udids=controller.resolve_devices(args.udid or [row['udid'] for row in controller.discover()])
    if not 1024 <= args.port <= 65535 or not 1024 <= args.base_port <= 65535-len(udids)+1:
        raise ValueError('Invalid ports')
    if args.port in range(args.base_port,args.base_port+len(udids)):
        raise ValueError('Dashboard and device ports must be different')
    token=secrets.token_urlsafe(32)
    devices=[{'udid':udid,'name':f'iPhone {index+1}', 'port':args.base_port+index}
             for index,udid in enumerate(udids)]
    manager=FocusManager(devices,token)
    children={}
    from text_translation import TextTranslationService
    from translation_routes import dispatch
    from translation import TranslationError
    translation_service=TextTranslationService()

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
                return self.respond(200,(ROOT/'web/dashboard.html').read_bytes(),'text/html; charset=utf-8')
            if self.path!='/api/state':
                return self.respond(404,{'error':'not found'})
            rows=[]
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for device in devices:
                ready=False
                child=children.get(device['udid'])
                if child and child.poll() is None:
                    try:
                        with opener.open(f"http://127.0.0.1:{device['port']}/",timeout=0.5) as response:
                            ready=response.status==200
                    except OSError:
                        pass
                rows.append({**device,'ready':ready,'active':manager.active==device['udid']})
            return self.respond(200,{'devices':rows,'active':manager.active})

        def do_POST(self):
            if not self.allowed():
                return self.respond(403,{'error':'same-origin localhost access required'})
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
                manager.select(body['udid'])
                return self.respond(200,{'active':manager.active})
            except (ValueError, KeyError, TypeError):
                return self.respond(400,{'error':'invalid device selection'})
            except Exception:
                return self.respond(503,{'error':'设备切换未完成，请稍后重试','active':manager.active})

    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    try:
        for device in devices:
            port=device['port']
            env={**os.environ,'IPHONE_BATCH_CONTROL_TOKEN':token,'IPHONE_BATCH_TRANSLATION_URL':f'http://127.0.0.1:{args.port}/internal/translation'}
            logs=ROOT/'.device-data'/'diagnostics'
            logs.mkdir(parents=True,exist_ok=True)
            with (logs/f'dashboard-{port}.log').open('wb') as output:
                children[device['udid']]=subprocess.Popen(
                    [sys.executable,str(ROOT/'controller.py'),'screen','--udid',device['udid'],'--port',str(port)],
                    env=env,stdout=output,stderr=subprocess.STDOUT,
                    creationflags=0x08000000 if os.name=='nt' else 0)
        controller.emit({'status':'dashboard_ready','url':f'http://127.0.0.1:{args.port}/','devices':devices})
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        # Stop children and their upstream viewers even when the parent exits.
        import psutil
        for child in children.values():
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
