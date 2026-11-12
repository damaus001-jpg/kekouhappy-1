"""Optional D3D11 decode and bounded buffer reuse; actual mode is reported."""
import contextlib
import json
from pathlib import Path
import re
import time


class CodecFactory:
    def __init__(self,av_module,*,gpu=False,memory=True,status_path=None):
        self.av=av_module
        self.gpu_requested=gpu
        self.memory=memory
        self.status_path=Path(status_path) if status_path else None
        self.gpu_failed=False
        self.on_runtime_failure=None
        self.state={}

    def report(self,decoder,reason=''):
        state={'gpu_requested':self.gpu_requested,'decoder':decoder,
               'memory_optimized':self.memory,'reason':reason}
        if state==self.state:return
        self.state=state
        if self.status_path:
            with contextlib.suppress(OSError):
                self.status_path.parent.mkdir(parents=True,exist_ok=True)
                temp=self.status_path.with_suffix('.tmp')
                temp.write_text(json.dumps({**state,'updated':time.time()},ensure_ascii=False),encoding='utf-8')
                temp.replace(self.status_path)

    def context(self,name,mode,gpu):
        if gpu:
            from av.codec.hwaccel import HWAccel
            ctx=self.av.codec.CodecContext.create(name,mode,hwaccel=HWAccel('d3d11va',allow_software_fallback=False,is_hw_owned=False))
        else:ctx=self.av.codec.CodecContext.create(name,mode)
        ctx.thread_count=1
        ctx.thread_type='SLICE'
        return ctx

    def create(self,name,mode=None):
        gpu=self.gpu_requested and not self.gpu_failed
        try:ctx=self.context(name,mode,gpu)
        except Exception as exc:
            if not gpu:raise
            self.gpu_failed=True
            self.report('cpu-fallback',str(exc))
            ctx=self.context(name,mode,False)
            gpu=False
        if not self.state:self.report('gpu-initializing' if gpu else 'cpu')
        return CodecProxy(self,ctx,name,mode,gpu)


class CodecProxy:
    def __init__(self,factory,ctx,name,mode,gpu):
        self.factory,self.ctx=factory,ctx
        self.name,self.mode,self.gpu=name,mode,gpu
        self.emitted=False
        self.startup=[]
        self.startup_bytes=0
        self.failed=False

    def decode(self,packet):
        if self.failed:return []
        if self.gpu and not self.emitted and packet is not None:
            raw=bytes(packet)
            self.startup_bytes+=len(raw)
            if self.startup_bytes>16*1024*1024:
                return self.fallback(ValueError('GPU 初始化未输出画面，启动缓冲达到上限'))
            self.startup.append(raw)
        try:frames=list(self.ctx.decode(packet))
        except Exception as exc:
            if not self.gpu:raise
            if not self.emitted and isinstance(exc,self.factory.av.error.InvalidDataError) and packet is not None:
                raw=bytes(packet)
                if not any(n and ((n[0]>>1)&0x3f)<32 for n in re.split(b'\x00\x00\x00?\x01',raw)):
                    return []
            if self.emitted and isinstance(exc,self.factory.av.error.InvalidDataError):raise
            if not self.emitted:return self.fallback(exc)
            self.failed=True
            self.factory.gpu_failed=True
            self.factory.report('cpu-restarting',str(exc))
            if self.factory.on_runtime_failure:self.factory.on_runtime_failure(str(exc))
            return []
        if frames:
            if self.gpu and bool(self.ctx.is_hwaccel):self.factory.report('gpu-d3d11va')
            elif self.factory.gpu_requested:self.factory.report('cpu-fallback',self.factory.state.get('reason') or '硬件解码未实际启用')
            else:self.factory.report('cpu')
            self.emitted=True
            self.startup.clear()
        return frames

    def fallback(self,error):
        self.factory.gpu_failed=True
        self.factory.report('cpu-fallback',str(error))
        with contextlib.suppress(Exception):self.ctx.close()
        self.ctx=self.factory.context(self.name,self.mode,False)
        self.gpu=False
        frames=[]
        for raw in self.startup:
            try:frames.extend(self.ctx.decode(self.factory.av.Packet(raw)))
            except self.factory.av.error.InvalidDataError:
                # Parameter-set-only bootstrap packets legitimately emit none.
                if any(n and ((n[0]>>1)&0x3f)<32 for n in re.split(b'\x00\x00\x00?\x01',raw)):
                    raise
        self.startup.clear()
        self.emitted=bool(frames)
        return frames

    def close(self):
        self.startup.clear()
        with contextlib.suppress(Exception):self.ctx.close()


def emit_with_reused_buffers(transcoder,frame,av_module):
    formatter=getattr(transcoder,'_reused_formatter',None)
    if formatter is None:
        formatter=av_module.video.reformatter.VideoReformatter()
        transcoder._reused_formatter=formatter
    output=formatter.reformat(frame,width=transcoder.width,height=transcoder.height,format='bgra')
    plane=output.planes[0]
    row_bytes=transcoder.width*4
    required=row_bytes*transcoder.height
    buffer=getattr(transcoder,'_reused_pixels',None)
    if buffer is None or len(buffer)!=required:
        buffer=bytearray(required)
        transcoder._reused_pixels=buffer
        transcoder._reused_alpha=b'\xff'*(required//4)
    source=memoryview(plane)
    target=memoryview(buffer)
    if plane.line_size==row_bytes:target[:]=source[:required]
    else:
        for row in range(transcoder.height):
            target[row*row_bytes:(row+1)*row_bytes]=source[row*plane.line_size:row*plane.line_size+row_bytes]
    buffer[3::4]=transcoder._reused_alpha
    # An immutable handoff protects the frame currently being sent over RFB;
    # the reusable working buffer must never overwrite that in-flight frame.
    transcoder._on_frame(bytes(buffer))


def install_queue_guard(transcoder_class,on_backlog,limit=32):
    original=transcoder_class.feed
    def feed(self,annexb):
        if getattr(self,'_resync_pending',False):return
        if self._inq.qsize()>=limit:
            self._resync_pending=True
            # A compressed delta cannot be dropped in isolation. Request a
            # fresh stream/decoder so its next frame starts a valid chain.
            on_backlog()
            return
        original(self,annexb)
    transcoder_class.feed=feed
