"""Experimental AV continuous-decode run; original source stays untouched.

The baseline stalls after client-connect arms _refresh_pending: RTP keeps
arriving but no requested IDR arrives, so feed_count stops permanently.
This run disables forced decoder refreshes to check continuous AV decoding.
"""
import logging
import asyncio
import os
import sys
import time
from types import SimpleNamespace
from pathlib import Path

source = Path(__file__).resolve().parent / 'upstream-pymobiledevice3-v11.51.0'
sys.path.insert(0, str(source))
from pymobiledevice3.remote.core_device.vnc_server import VncStreamServer
from PIL import Image

# A successful phone-side pairing can be saved locally even when Apple's
# usbmux SavePairRecord fails. Prefer the already-validated project identity;
# leave the upstream checkout and the system pairing database untouched.
from pymobiledevice3 import lockdown
from pymobiledevice3.pair_records import get_local_pairing_record
original_pair_lookup = lockdown.get_preferred_pair_record
project_data = Path(__file__).resolve().parent


async def project_pair_lookup(identifier, pairing_records_cache_folder, usbmux_address=None):
    record = get_local_pairing_record(identifier, project_data)
    if record:
        return record
    return await original_pair_lookup(identifier, pairing_records_cache_folder, usbmux_address)


lockdown.get_preferred_pair_record = project_pair_lookup
sys.path.append(str(project_data.parent))
from pairing_patch import prevent_automatic_pairing
prevent_automatic_pairing()

from pymobiledevice3.services import cryptexd
cached_ddi = project_data / 'Xcode_iOS_DDI_Cryptex'
if (cached_ddi / 'BuildManifest.plist').is_file() and (cached_ddi / 'Image.dmg').is_file():
    cryptexd.fetch_cryptex_ddi = lambda: cached_ddi

# Configure the codec before its first decode/open. All phones share the CPU;
# allowing every codec to allocate the full machine's thread count scales badly.
from pymobiledevice3.remote.core_device import hevc_av
av_module = hevc_av._av


mode_path = Path(__file__).resolve().parent / 'native-vnc-display-mode.json'
port = sys.argv[sys.argv.index('--port')+1] if '--port' in sys.argv else '5901'
from native_decode_accel import CodecFactory,emit_with_reused_buffers,install_queue_guard
memory_optimized=os.environ.get('VNC_MEMORY_OPT','1')=='1'
codec_factory=CodecFactory(av_module,gpu=os.environ.get('VNC_GPU_ACCEL','0')=='1',
    memory=memory_optimized,status_path=project_data/'diagnostics'/f'accel-{port}.json')
hevc_av._av = SimpleNamespace(codec=SimpleNamespace(CodecContext=codec_factory),
                              Packet=av_module.Packet, error=av_module.error)
original_emit = hevc_av.HevcToBgraTranscoder._emit_frame


def paced_emit(self, frame):
    now = time.monotonic()
    fps = float(os.environ.get('VNC_PRESENT_FPS', '0'))
    if fps > 0:
        if now - getattr(self, '_mode_checked', 0) > .5:
            self._mode_checked = now
            try:
                import json
                mode = json.loads(mode_path.read_text(encoding='utf-8'))
                self._display_fps = float(mode.get('focus_fps', 5) if str(mode.get('focus_port')) == port else mode.get('grid_fps', fps))
            except (OSError, ValueError):
                self._display_fps = fps
        fps = max(1, getattr(self, '_display_fps', fps))
        if now - getattr(self, '_last_present', 0) < 1 / fps:
            return
        self._last_present = now
    if memory_optimized:emit_with_reused_buffers(self,frame,av_module)
    else:original_emit(self, frame)


hevc_av.HevcToBgraTranscoder._emit_frame = paced_emit

original_new_transcoder=VncStreamServer._new_transcoder
backlog_callback=None
def request_backlog_resync():
    if backlog_callback is not None:backlog_callback()
if memory_optimized:install_queue_guard(hevc_av.HevcToBgraTranscoder,request_backlog_resync)
def acceleration_transcoder(self,*args,**kwargs):
    global backlog_callback
    def failed(reason):
        def schedule():
            task=getattr(self,'_gpu_fallback_task',None)
            if task is None or task.done():
                self._gpu_fallback_task=asyncio.create_task(self._switch_video())
        if self._loop is not None:self._loop.call_soon_threadsafe(schedule)
    codec_factory.on_runtime_failure=failed
    backlog_callback=lambda:failed('compressed input queue exceeded bounded limit')
    return original_new_transcoder(self,*args,**kwargs)
VncStreamServer._new_transcoder=acceleration_transcoder

# Prepare only a phone being operated, before dispatching its first touch.
# Monitoring alone should not register eighteen external keyboards at once.
from native_keyboard_policy import install_keyboard_policy
from native_device_control import ControlPolicy
install_keyboard_policy(VncStreamServer,control_allowed=ControlPolicy(port))


class QuietFrameRequests(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith('FramebufferUpdateRequest')


logging.getLogger('pymobiledevice3.remote.core_device.vnc_server').addFilter(QuietFrameRequests())
original_present = VncStreamServer._present
preview_width = int(os.environ.get('VNC_PREVIEW_WIDTH', '416'))


def fast_present(self, bgra, width, height):
    frame, w, h, rotation = original_present(self, bgra, width, height)
    if preview_width > 0 and w > preview_width:
        target = (preview_width, max(1, round(h * preview_width / w)))
        image = Image.frombytes('RGBA', (w, h), frame, 'raw', 'BGRA')
        frame = image.resize(target, Image.Resampling.BILINEAR).tobytes('raw', 'BGRA')
        w, h = target
    return frame, w, h, rotation


def continuous_decode(self, now, *, reason):
    self._last_refresh_t = now
    if not getattr(self, '_continuous_notice', False):
        logging.getLogger('vnc_av_continuous').warning(
            'EXPERIMENTAL: forced keyframe wait disabled for continuous AV decoding; trigger=%s', reason)
        self._continuous_notice = True


VncStreamServer._fire_decoder_refresh = continuous_decode
VncStreamServer._present = fast_present
from pymobiledevice3.__main__ import main

sys.exit(main())
