from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

import av
from native_decode_accel import CodecFactory,emit_with_reused_buffers,install_queue_guard


def frame(width=320,height=640,luma=40):
    image=av.VideoFrame(width,height,'yuv420p')
    for index,plane in enumerate(image.planes):
        plane.update(bytes([luma if index==0 else 128])*plane.buffer_size)
    return image


class AccelerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        encoder=av.CodecContext.create('libx265','w')
        encoder.width,encoder.height=320,640
        encoder.pix_fmt='yuv420p'
        encoder.time_base=Fraction(1,30)
        encoder.framerate=Fraction(30,1)
        encoder.thread_count=1
        encoder.options={'preset':'ultrafast','tune':'zerolatency',
            'x265-params':'pools=none:frame-threads=1:log-level=error:repeat-headers=1:keyint=10'}
        cls.packets=[]
        for i in range(6):
            image=frame(luma=40+i*10)
            image.pts=i
            cls.packets.extend(bytes(p) for p in encoder.encode(image))
        cls.packets.extend(bytes(p) for p in encoder.encode(None))

    def test_real_hardware_decode_or_reported_cpu_fallback(self):
        factory=CodecFactory(av,gpu=True)
        decoder=factory.create('hevc','r')
        result=[]
        for packet in self.packets:result.extend(decoder.decode(av.Packet(packet)))
        result.extend(decoder.decode(None))
        self.assertEqual(len(result),6)
        self.assertIn(factory.state['decoder'],('gpu-d3d11va','cpu-fallback'))
        print('REAL HEVC PROBE:',factory.state,flush=True)
        decoder.close()

    def test_gpu_initialization_failure_replays_startup_on_cpu(self):
        factory=CodecFactory(av,gpu=True)
        real=factory.context
        def context(name,mode,gpu):
            if gpu:return SimpleNamespace(decode=Mock(side_effect=RuntimeError('GPU unavailable')),close=lambda:None)
            return real(name,mode,False)
        factory.context=context
        decoder=factory.create('hevc','r')
        result=[]
        for packet in self.packets:result.extend(decoder.decode(av.Packet(packet)))
        result.extend(decoder.decode(None))
        self.assertEqual(len(result),6)
        self.assertEqual(factory.state['decoder'],'cpu-fallback')
        self.assertIn('GPU unavailable',factory.state['reason'])

    def test_runtime_gpu_failure_requests_fresh_cpu_stream(self):
        factory=CodecFactory(av,gpu=True)
        callback=Mock()
        factory.on_runtime_failure=callback
        real=factory.context
        fake=SimpleNamespace(is_hwaccel=True,decode=Mock(side_effect=[[object()],RuntimeError('device lost')]),close=lambda:None)
        factory.context=lambda name,mode,gpu:fake if gpu else real(name,mode,False)
        decoder=factory.create('hevc','r')
        decoder.decode(av.Packet(b'first'))
        decoder.decode(av.Packet(b'second'))
        callback.assert_called_once_with('device lost')
        self.assertTrue(factory.gpu_failed)
        self.assertFalse(factory.create('hevc','r').gpu)

    def test_reused_buffer_does_not_mutate_in_flight_frame(self):
        outputs=[]
        transcoder=SimpleNamespace(width=320,height=640,_on_frame=outputs.append)
        emit_with_reused_buffers(transcoder,frame(luma=40),av)
        working=id(transcoder._reused_pixels)
        previous=outputs[0]
        emit_with_reused_buffers(transcoder,frame(luma=90),av)
        self.assertEqual(id(transcoder._reused_pixels),working)
        self.assertEqual(outputs[0],previous)
        self.assertNotEqual(outputs[0],outputs[1])
        self.assertEqual(len(outputs[0]),320*640*4)
        self.assertEqual(outputs[0][3::4],b'\xff'*(320*640))

    def test_queue_overflow_requests_stream_restart_once(self):
        callback=Mock()
        class Transcoder:
            def feed(self,packet):self.accepted.append(packet)
        install_queue_guard(Transcoder,callback,limit=2)
        decoder=Transcoder()
        decoder.accepted=[]
        decoder._inq=SimpleNamespace(qsize=lambda:2)
        decoder.feed(b'old-delta')
        decoder.feed(b'later-delta')
        callback.assert_called_once()
        self.assertEqual(decoder.accepted,[])


if __name__=='__main__':unittest.main()
