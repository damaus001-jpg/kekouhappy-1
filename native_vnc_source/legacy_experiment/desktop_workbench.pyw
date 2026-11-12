"""Open the existing authenticated 8070 workbench as a native desktop client."""
from __future__ import annotations

import hmac
import http.cookies
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        for parent in Path(sys.executable).resolve().parents:
            if (parent / "iphone_batch" / "dashboard.py").is_file():
                return parent
            if parent.name.lower() == "iphone_batch" and (parent / "dashboard.py").is_file():
                return parent.parent
    return Path(__file__).resolve().parents[2]


PROJECT = project_root()
SCRIPTS = PROJECT / "iphone_batch"
UPSTREAM = "http://127.0.0.1:8070"
VNC_DEVICES = {
    5901: "00008030-001275241E8B802E",
    5902: "00008030-001225443E33C02E",
    5903: "00008030-000315A00EB9402E",
    5904: "00008030-001515510132402E",
    5905: "00008030-001268E626C0C02E",
    5906: "00008030-000E60161E79402E",
    5907: "00008030-001944362185402E",
    5908: "00008030-001838463A78802E",
    5909: "00008030-001D25540A91802E",
    5910: "00008030-001619C136F2802E",
    5911: "00008030-001E301922D8402E",
    5912: "00008030-001C481A3C32802E",
}
FRAME_LOCK = threading.Lock()
FRAMES: dict[str, bytes] = {}
FRAME_VERSIONS: dict[str, int] = {}
VNC_SEND_LOCKS = {udid: threading.Lock() for udid in VNC_DEVICES.values()}
VNC_SIZES: dict[str, tuple[int, int]] = {}
VNC_SOCKETS: dict[str, socket.socket] = {}
STOP_FRAMES = threading.Event()
LOG_PATH = SCRIPTS / ".device-data" / "logs" / "desktop-client.log"
LOG_LOCK = threading.Lock()


def log_event(message: str):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_LOCK, LOG_PATH.open("a", encoding="utf-8") as output:
            output.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass

sys.path.insert(0, str(SCRIPTS))
from workspace_access import HEADER, signed_header, signed_opener  # noqa: E402


APP_CSS = """
<style id="desktop-workbench-layout">
html{scroll-behavior:smooth;scrollbar-gutter:stable;overflow-y:scroll}
body{overflow-y:scroll;scrollbar-gutter:stable;overflow-anchor:none}
.global-monitor{width:100%;max-width:none;box-sizing:border-box;padding:12px 16px 18px;scrollbar-gutter:stable;overflow-anchor:none}
.global-monitor:fullscreen,.global-monitor.monitor-window-fullscreen{width:100vw;height:100vh;box-sizing:border-box;overflow-y:scroll!important;scrollbar-gutter:stable}
.monitor-header{gap:12px;margin-bottom:8px}
.monitor-header h1{font-size:22px;margin:0}
.monitor-header p{margin:2px 0;font-size:12px}
.monitor-grid{display:grid;width:100%;box-sizing:border-box;grid-template-columns:repeat(10,minmax(0,1fr))!important;grid-auto-flow:row;gap:7px;align-items:start;overflow-anchor:none}
.monitor-tile{width:100%;min-width:0;box-sizing:border-box;border-radius:7px;transform:none}
.monitor-tile-heading{min-height:26px;padding:4px 6px;font-size:11px}
.monitor-screen{width:100%;min-width:0;flex:none;aspect-ratio:9/19.5}
.monitor-screen img{position:absolute;inset:0;width:100%;height:100%;max-width:100%;max-height:100%;object-fit:contain;transform:none;margin:0;padding:0}
.monitor-state,.monitor-followup{font-size:9px;line-height:1.25;padding:3px 5px}
@media(max-width:1100px){.monitor-grid{grid-template-columns:repeat(10,minmax(0,1fr))!important;gap:4px}.monitor-tile-heading{font-size:9px;padding:3px}.monitor-state,.monitor-followup{font-size:8px;padding:2px 3px}}
#desktop-focus{position:fixed;inset:0;z-index:2000;background:#080b09f5;display:grid;grid-template-rows:54px minmax(0,1fr);padding:8px 14px 14px;box-sizing:border-box}
#desktop-focus[hidden]{display:none}#desktop-focus header{display:flex;align-items:center;justify-content:space-between;color:#eeeadd;font-size:16px}
#desktop-focus button{padding:6px 18px}#desktop-focus img{display:block;width:100%;height:100%;object-fit:contain;touch-action:none;user-select:none;background:#080b09;transform:none}
#selected{position:relative}
#selected.desktop-vnc-active>:not(#desktop-selected-overlay){visibility:hidden!important}
#desktop-selected-overlay{position:absolute;inset:0;z-index:8;display:grid;place-items:center;overflow:hidden;background:#101510}
#desktop-selected-overlay[hidden]{display:none}
#desktop-selected-overlay img{display:block;width:100%;height:100%;object-fit:contain;touch-action:none;user-select:none}
</style>
"""

APP_JS = """
<script>
(()=>{const frames=new Map();let running=false,focusDevice='';
 const isFullscreen=()=>{const s=document.getElementById('global-monitor');return !!s&&(document.fullscreenElement===s||s.classList.contains('monitor-window-fullscreen'));};
 const focus=document.createElement('section');focus.id='desktop-focus';focus.hidden=true;focus.innerHTML='<header><strong></strong><button type="button">关闭大画面 · Esc</button></header><img alt="手机实时画面">';document.body.append(focus);
 const focusImage=focus.querySelector('img'),focusTitle=focus.querySelector('strong');
 const selected=document.getElementById('selected'),selectedOverlay=document.createElement('div');selectedOverlay.id='desktop-selected-overlay';selectedOverlay.hidden=true;selectedOverlay.innerHTML='<img alt="所选手机实时画面">';if(selected)selected.append(selectedOverlay);const selectedImage=selectedOverlay.querySelector('img');
 function bindInput(image){if(image.dataset.vncInput)return;image.dataset.vncInput='1';let buttons=0,lastMove=0;
  const send=(kind,fields)=>fetch('/desktop-input',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:image.dataset.device,kind,...fields})}).catch(()=>{});
  const point=(event)=>{const rect=image.getBoundingClientRect(),iw=image.naturalWidth||832,ih=image.naturalHeight||1808,box=rect.width/rect.height,ratio=iw/ih;let w=rect.width,h=rect.height,left=0,top=0;if(ratio<box){w=rect.height*ratio;left=(rect.width-w)/2;}else{h=rect.width/ratio;top=(rect.height-h)/2;}return{x:Math.max(0,Math.min(1,(event.clientX-rect.left-left)/w)),y:Math.max(0,Math.min(1,(event.clientY-rect.top-top)/h))};};
  image.addEventListener('pointerdown',event=>{if(!image.closest('#desktop-focus')&&isFullscreen())return;const p=point(event);buttons=1;image.setPointerCapture(event.pointerId);send('pointer',{...p,buttons});image.focus();});
  image.addEventListener('pointermove',event=>{if(!buttons||Date.now()-lastMove<30)return;lastMove=Date.now();send('pointer',{...point(event),buttons});});
  const release=event=>{if(!buttons)return;buttons=0;send('pointer',{...point(event),buttons:0});};image.addEventListener('pointerup',release);image.addEventListener('pointercancel',release);
  const keymap={Enter:0xff0d,Escape:0xff1b,Backspace:0xff08,Tab:0xff09,ArrowLeft:0xff51,ArrowUp:0xff52,ArrowRight:0xff53,ArrowDown:0xff54,Delete:0xffff,Home:0xff50,End:0xff57,PageUp:0xff55,PageDown:0xff56};
  const keycode=event=>keymap[event.key]||(event.key.length===1?event.key.toLowerCase().charCodeAt(0):0);
  image.addEventListener('keydown',event=>{if(event.key==='Escape'&&focusDevice){focus.hidden=true;focusDevice='';return;}const key=keycode(event);if(key){event.preventDefault();send('key',{keysym:key,down:true});}});
  image.addEventListener('keyup',event=>{const key=keycode(event);if(key){event.preventDefault();send('key',{keysym:key,down:false});}});
 }
 function openFocus(tile){focusDevice=tile.dataset.udid;focusTitle.textContent=tile.querySelector('.monitor-tile-heading strong')?.textContent||tile.title||'手机画面';const image=tile.querySelector('.monitor-screen img');focusImage.dataset.device=focusDevice;focusImage.src=image?.src||'';focus.hidden=false;bindInput(focusImage);}
 focus.querySelector('button').addEventListener('click',()=>{focus.hidden=true;focusDevice='';});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!focus.hidden){focus.hidden=true;focusDevice='';event.stopPropagation();}},true);
 document.addEventListener('click',event=>{if(!isFullscreen()||event.target.closest('#desktop-focus'))return;const tile=event.target.closest('.monitor-tile[data-udid]');if(!tile)return;event.preventDefault();event.stopImmediatePropagation();openFocus(tile);},true);
 async function refresh(){if(running)return;running=true;try{
 for(const tile of document.querySelectorAll('.monitor-tile[data-udid]')){
  const id=tile.dataset.udid,image=tile.querySelector('.monitor-screen img');if(!image)continue;
  try{const response=await fetch('/desktop-frame?device='+encodeURIComponent(id),{cache:'no-store'});if(!response.ok)continue;
   const version=response.headers.get('X-Frame-Version')||'';
   if(version&&version===image.dataset.frameVersion&&image.src===image.dataset.desktopSrc)continue;
   const blob=await response.blob(),old=frames.get(id),next=URL.createObjectURL(blob);frames.set(id,next);image.src=next;image.hidden=false;image.dataset.device=id;image.dataset.frameVersion=version;image.dataset.desktopSrc=image.src;
   bindInput(image);image.style.touchAction='none';image.style.userSelect='none';image.tabIndex=0;image.title='点击或拖动可直接控制手机';
   if(focusDevice===id){focusImage.src=next;focusImage.dataset.device=id;}
   const placeholder=tile.querySelector('.monitor-placeholder');if(placeholder)placeholder.hidden=true;
   const state=tile.querySelector('.monitor-state');if(state)state.textContent='独立投屏 · 实时画面';
   if(old)URL.revokeObjectURL(old);
  }catch(_){ }
 }
 const selectedTile=document.querySelector('.monitor-tile.monitor-selected[data-udid]'),selectedId=selectedTile?.dataset.udid,selectedFrame=selectedId?frames.get(selectedId):null;
 if(selected&&selectedFrame){selectedImage.dataset.device=selectedId;selectedImage.src=selectedFrame;selectedOverlay.hidden=false;selected.classList.add('desktop-vnc-active');bindInput(selectedImage);}else if(selected){selectedOverlay.hidden=true;selected.classList.remove('desktop-vnc-active');}
 const all=document.querySelectorAll('.monitor-tile[data-udid]').length,shown=[...document.querySelectorAll('.monitor-screen img')].filter(image=>!image.hidden&&image.dataset.frameVersion).length;const count=document.getElementById('monitor-count');if(count)count.textContent=all+' 台设备 · '+shown+' 台已显示 · '+shown+' 台 VNC 投屏就绪';
 }finally{running=false;}}
 setInterval(refresh,400);document.addEventListener('DOMContentLoaded',refresh);window.addEventListener('pagehide',()=>frames.forEach(URL.revokeObjectURL));
})();
</script>
"""


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    if size < 0 or size > 32 * 1024 * 1024:
        raise ValueError(f"Invalid RFB payload length: {size}")
    chunks = bytearray()
    while len(chunks) < size:
        block = sock.recv(size - len(chunks))
        if not block:
            raise ConnectionError("VNC server disconnected")
        chunks.extend(block)
    return bytes(chunks)


def _read_vnc(port: int, udid: str):
    """Minimal RFB 3.8 client for the upstream server's Raw BGRA frames."""
    while not STOP_FRAMES.is_set():
        sock = None
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=5)
            sock.settimeout(300)
            if _recv_exact(sock, 12) != b"RFB 003.008\n":
                raise ConnectionError("Unexpected RFB version")
            sock.sendall(b"RFB 003.008\n")
            if _recv_exact(sock, 2) != b"\x01\x02":
                raise ConnectionError("VNC Auth unavailable")
            sock.sendall(b"\x02")
            _recv_exact(sock, 16)  # The local server has no password configured.
            sock.sendall(bytes(16))
            if _recv_exact(sock, 4) != b"\x00\x00\x00\x00":
                raise ConnectionError("VNC authentication failed")
            sock.sendall(b"\x01")
            init = _recv_exact(sock, 24)
            width, height = struct.unpack(">HH", init[:4])
            if not (100 <= width <= 4096 and 100 <= height <= 8192):
                raise ValueError(f"Unexpected framebuffer size {width}x{height}")
            log_event(f"VNC {port} ({udid[-8:]}) connected, {width}x{height}")
            with FRAME_LOCK:
                VNC_SIZES[udid] = (width, height)
            name_len = struct.unpack(">I", init[20:24])[0]
            _recv_exact(sock, name_len)
            # Raw framebuffer + DesktopSize. The server sends BGRA/BGRX bytes.
            sock.sendall(b"\x02\x00\x00\x02" + struct.pack(">ii", 0, -223))
            log_event(f"VNC {port} ({udid[-8:]}) sent Raw/DesktopSize encodings")
            with FRAME_LOCK:
                VNC_SOCKETS[udid] = sock
            incremental = 0
            while not STOP_FRAMES.is_set():
                with VNC_SEND_LOCKS[udid]:
                    sock.sendall(b"\x03" + bytes([incremental]) + struct.pack(">HHHH", 0, 0, width, height))
                incremental = 1
                message_type = _recv_exact(sock, 1)[0]
                log_event(f"VNC {port} ({udid[-8:]}) server message type {message_type}")
                if message_type != 0:
                    raise ConnectionError(f"Unexpected RFB message {message_type}")
                _recv_exact(sock, 1)
                rect_count = struct.unpack(">H", _recv_exact(sock, 2))[0]
                log_event(f"VNC {port} ({udid[-8:]}) framebuffer update rects={rect_count}")
                for _ in range(rect_count):
                    header = _recv_exact(sock, 12)
                    _x, _y, rect_w, rect_h, encoding = struct.unpack(">HHHHi", header)
                    log_event(f"VNC {port} ({udid[-8:]}) rect={rect_w}x{rect_h} encoding={encoding}")
                    if encoding == -223:
                        width, height = rect_w, rect_h
                        if not (100 <= width <= 4096 and 100 <= height <= 8192):
                            raise ValueError(f"Invalid DesktopSize {width}x{height}")
                        with FRAME_LOCK:
                            VNC_SIZES[udid] = (width, height)
                        continue
                    if encoding != 0:
                        raise ConnectionError(f"Unsupported framebuffer encoding {encoding}")
                    if rect_w == 0 or rect_h == 0 or rect_w * rect_h * 4 > 32 * 1024 * 1024:
                        raise ValueError(f"Invalid raw rect {rect_w}x{rect_h}")
                    pixels = _recv_exact(sock, rect_w * rect_h * 4)
                    from PIL import Image

                    image = Image.frombytes("RGB", (rect_w, rect_h), pixels, "raw", "BGRX")
                    image.thumbnail((320, 700), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    image.save(output, format="JPEG", quality=48, optimize=True)
                    encoded = output.getvalue()
                    with FRAME_LOCK:
                        if FRAMES.get(udid) != encoded:
                            FRAMES[udid] = encoded
                            FRAME_VERSIONS[udid] = FRAME_VERSIONS.get(udid, 0) + 1
                STOP_FRAMES.wait(0.25)
        except Exception as error:
            log_event(f"VNC {port} ({udid[-8:]}) disconnected: {type(error).__name__}: {error}")
            with FRAME_LOCK:
                FRAMES.pop(udid, None)
                FRAME_VERSIONS.pop(udid, None)
        finally:
            with FRAME_LOCK:
                if VNC_SOCKETS.get(udid) is sock:
                    VNC_SOCKETS.pop(udid, None)
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        STOP_FRAMES.wait(3)


def start_frame_readers():
    for port, udid in VNC_DEVICES.items():
        threading.Thread(
            target=_read_vnc, args=(port, udid), name=f"vnc-frame-{port}", daemon=True
        ).start()


class WorkbenchProxy(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        self.launch_key = secrets.token_urlsafe(32)
        self.cookie_key = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", 0), WorkbenchHandler)


class WorkbenchHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SMSWorkbenchDesktop"
    sys_version = ""

    def log_message(self, *_args):
        return

    def _deny(self, status=403):
        body = b"Desktop workbench access denied."
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _cookie(self):
        raw = self.headers.get("Cookie", "")
        parsed = http.cookies.SimpleCookie()
        try:
            parsed.load(raw)
            return parsed.get("sms_workbench_desktop")
        except http.cookies.CookieError:
            return None

    def _bootstrap(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/" or parsed.query != "launch=" + self.server.launch_key:
            return False
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"sms_workbench_desktop={self.server.cookie_key}; Path=/; HttpOnly; SameSite=Strict",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def _authorized(self):
        port = self.server.server_port
        if self.headers.get("Host") != f"127.0.0.1:{port}":
            return False
        origin = self.headers.get("Origin")
        expected_origin = f"http://127.0.0.1:{port}"
        if origin not in (None, expected_origin):
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        cookie = self._cookie()
        if cookie is None or not hmac.compare_digest(cookie.value, self.server.cookie_key):
            return False
        return True

    def _handle(self):
        if self.command not in ("GET", "POST", "HEAD"):
            return self._deny(405)
        if self._bootstrap():
            return
        if not self._authorized():
            return self._deny()

        parsed_path = urlsplit(self.path)
        if parsed_path.path == "/desktop-frame" and self.command in ("GET", "HEAD"):
            from urllib.parse import parse_qs

            udid = parse_qs(parsed_path.query).get("device", [""])[0]
            with FRAME_LOCK:
                frame = FRAMES.get(udid)
                version = FRAME_VERSIONS.get(udid, 0)
            if frame is None:
                return self._deny(404)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("X-Frame-Version", str(version))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(frame)
            return
        if parsed_path.path == "/desktop-input" and self.command == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 2048:
                    return self._deny(400)
                request = json.loads(self.rfile.read(length))
                udid = request.get("device")
                if udid not in VNC_SEND_LOCKS:
                    return self._deny(404)
                with FRAME_LOCK:
                    sock = VNC_SOCKETS.get(udid)
                    size = VNC_SIZES.get(udid)
                if sock is None or size is None:
                    return self._deny(503)
                if request.get("kind") == "pointer":
                    x = max(0, min(size[0] - 1, round(float(request["x"]) * (size[0] - 1))))
                    y = max(0, min(size[1] - 1, round(float(request["y"]) * (size[1] - 1))))
                    buttons = max(0, min(7, int(request.get("buttons", 0))))
                    message = struct.pack(">BBHH", 5, buttons, x, y)
                elif request.get("kind") == "key":
                    keysym = max(0, min(0x10FFFF, int(request["keysym"])))
                    message = struct.pack(">BB2xI", 4, int(bool(request.get("down"))), keysym)
                else:
                    return self._deny(400)
                with VNC_SEND_LOCKS[udid]:
                    sock.sendall(message)
                body = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (ValueError, TypeError, KeyError, OSError):
                self._deny(503)
            return

        target = UPSTREAM + self.path
        headers = {"Host": "127.0.0.1:8070", HEADER: signed_header(self.command, target)}
        for key in ("Accept", "Content-Type", "Cache-Control", "If-None-Match"):
            value = self.headers.get(key)
            if value:
                headers[key] = value
        data = None
        if self.command == "POST":
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._deny(400)
            if size < 0 or size > 32 * 1024 * 1024:
                return self._deny(413)
            data = self.rfile.read(size)
        request = urllib.request.Request(target, data=data, headers=headers, method=self.command)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(request, timeout=180)
            status, body, source_headers = response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            status, body, source_headers = error.code, error.read(), error.headers
        except (OSError, urllib.error.URLError, TimeoutError):
            return self._deny(502)

        if urlsplit(self.path).path == "/" and status == 200:
            body = body.replace(b"</head>", APP_CSS.encode("utf-8") + b"</head>", 1)
            body = body.replace(b"</body>", APP_JS.encode("utf-8") + b"</body>", 1)
        self.send_response(status)
        content_type = source_headers.get("Content-Type")
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    do_GET = _handle
    do_POST = _handle
    do_HEAD = _handle


def ensure_workbench():
    opener = signed_opener()
    try:
        with opener.open(UPSTREAM + "/api/state", timeout=3) as response:
            if response.status != 200:
                return False
    except (OSError, urllib.error.URLError):
        from backend_control import Backend

        Backend().start()
        for _ in range(30):
            time.sleep(1)
            try:
                with opener.open(UPSTREAM + "/api/state", timeout=1) as response:
                    if response.status == 200:
                        return True
            except (OSError, urllib.error.URLError):
                continue
        return False
    # Devices may have been reconnected after 8070 started. Refresh only
    # enumerates USB devices; it does not initiate trust pairing.
    request = urllib.request.Request(
        UPSTREAM + "/api/devices/refresh",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(request, timeout=20):
            pass
    except (OSError, urllib.error.URLError):
        pass
    return True


def show_error(message):
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "短信工作台", 0x10)
    except Exception:
        pass


def main():
    if not ensure_workbench():
        show_error("8070 短信工作台未能启动，请检查 .device-data\\logs 中的后台日志。")
        return
    server = WorkbenchProxy()
    start_frame_readers()
    threading.Thread(target=server.serve_forever, name="workbench-desktop-proxy", daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/?launch={server.launch_key}"
    try:
        import webview

        webview.create_window(
            "手机群控 · 短信工作台",
            url,
            width=1920,
            height=1080,
            min_size=(1100, 720),
            text_select=True,
        )
        webview.start(gui="edgechromium", debug=False)
    except Exception as error:
        log_event(f"Desktop window failed: {type(error).__name__}: {error}")
        show_error(f"桌面客户端窗口启动失败：{error}")
    finally:
        STOP_FRAMES.set()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log_event(f"Client startup failed: {type(error).__name__}: {error}")
        show_error(f"短信工作台启动失败：{error}")
