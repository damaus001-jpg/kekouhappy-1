"""Bounded, content-free video telemetry and shared source recovery budget."""
import asyncio
from time import monotonic
from collections import deque, OrderedDict
import math
import re
from contextvars import ContextVar

manual_restart = ContextVar('manual_video_restart', default=False)


class ForwardWriter:
    """Observe forwarding, without inspecting or retaining video bytes."""
    def __init__(self, owner, writer):
        self.owner, self.writer = owner, writer
        self.stats = {'bytes': 0, 'last_write_at': None, 'last_drain_at': None,
                      'drain_ms': 0, 'ended': False}
        if not hasattr(owner, '_video_forwards'):
            owner._video_forwards = deque(maxlen=64)
        owner._video_forwards.append(self.stats)

    def __getattr__(self, name):
        return getattr(self.writer, name)

    def write(self, data):
        self.writer.write(data)
        self.stats['bytes'] += len(data)
        self.stats['last_write_at'] = round(monotonic(), 3)

    async def drain(self):
        started = monotonic()
        try:
            await asyncio.wait_for(self.writer.drain(), 10)
        except Exception as error:
            event(self.owner, 'forward-failure-' + type(error).__name__)
            raise
        self.stats['last_drain_at'] = round(monotonic(), 3)
        self.stats['drain_ms'] = round(1000 * (monotonic() - started), 1)


def event(instance, reason):
    if not hasattr(instance, '_video_events'):
        instance._video_events = deque(maxlen=128)
    instance._video_events.append({'at': round(monotonic(), 3), 'reason': reason})


def record_browser(instance, report):
    """Accept only bounded numeric/enum telemetry, never arbitrary text/payloads."""
    if not isinstance(report,dict) or not re.fullmatch(r'[a-z0-9]{1,16}',str(report.get('client',''))):
        raise ValueError('invalid browser report')
    numeric={'receive_age_ms','submit_age_ms','decode_age_ms','paint_age_ms','queue','key_wait_ms',
             'packets','submitted','decoded','painted','decode_errors','queue_resets','reconnects',
             'paint_errors','paint_fallbacks','key_timeouts','reader_resyncs','page_restores'}
    boolean={'selected','hidden','pending_frame','draw_scheduled'}
    enums={'mode':{'connecting','hevc','jpeg'},'state':{'connecting','streaming','retrying'},
           'decoder_state':{'unconfigured','configured','closed','jpeg','unknown'}}
    clean={}
    if set(report)-numeric-boolean-set(enums)-{'client'}:raise ValueError('unexpected report fields')
    for key,value in report.items():
        if key=='client':continue
        if key in numeric:
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1e12):
                raise ValueError('invalid report number')
        elif key in boolean:
            if type(value) is not bool:raise ValueError('invalid report flag')
        elif key in enums:
            if value not in enums[key]:raise ValueError('invalid report state')
        clean[key]=value
    if not hasattr(instance,'_video_browser_reports'):instance._video_browser_reports=OrderedDict()
    reports=instance._video_browser_reports
    reports[report['client']]={'received_at':monotonic(),'values':clean}
    reports.move_to_end(report['client'])
    while len(reports)>16:reports.popitem(last=False)


def snapshot(instance):
    now = monotonic()
    states = getattr(instance, '_subscribers', {})
    task = getattr(instance, '_active_recv_task', None)
    return {'at': round(now, 3),
            'source_active': getattr(instance, '_active_service', None) is not None,
            'receiver_done': task.done() if task is not None else None,
            'rtp_packets': getattr(instance, '_rtp_packets_received', 0),
            'last_packet_observed_age_ms': round(1000 * (now - instance._video_packet_at))
                if hasattr(instance, '_video_packet_at') else None,
            'last_au_age_ms': round(1000 * (now - instance._last_good_au_t))
                if getattr(instance, '_last_good_au_t', 0) else None,
            'last_input_age_ms': round(1000*(now-instance._batch_last_input))
                if getattr(instance,'_batch_last_input',0) else None,
            'subscribers': [{'queue': q.qsize(), 'waiting_key': s.needs_key,
                'key_wait_ms': round(1000 * (now - s.needs_key_since)) if s.needs_key else 0}
                for q, s in list(states.items())[:64]],
            'events': list(getattr(instance, '_video_events', ())),
            'forwards': list(getattr(instance, '_video_forwards', ())),
            'browser': [{'client':client,'report_age_ms':round(1000*(now-report['received_at'])),
                         **report['values']} for client,report in getattr(instance,'_video_browser_reports',{}).items()],
            'jpeg': getattr(getattr(instance, '_jpeg_hub', None), 'diagnostics', None)}


def install(server):
    fresh = server._ensure_fresh_stream
    send_pli = server._send_rtcp_pli

    async def bounded_fresh(self, force=False):
        # Bootstrap, manual /restart and receiver recovery share one budget.
        # Reserve before awaiting: concurrent subscribers cannot each restart.
        now = monotonic()
        if not hasattr(self, '_video_restarts'):
            self._video_restarts = deque(maxlen=3)
        if force:
            task = getattr(self, '_active_recv_task', None)
            states = list(getattr(self, '_subscribers', {}).values())
            waiting = [s for s in states if s.needs_key]
            # Upstream bootstrap escalates after 3s even on a silent display.
            # Require evidence of continuing AUs after the key request, unless
            # the receiver ended or the user explicitly clicked restart.
            if (waiting and task is not None and not task.done()
                    and not manual_restart.get()
                    and not any(getattr(self, '_last_good_au_t', 0) > s.needs_key_since + 1
                                for s in waiting)):
                event(self, 'source-restart-suppressed-silent-bootstrap')
                return
            recent = self._video_restarts
            while recent and now - recent[0] >= 300:
                recent.popleft()
            if recent and (now - recent[-1] < 30 or len(recent) >= 3):
                event(self, 'source-restart-suppressed-budget')
                return
            recent.append(now)
        if force or getattr(self,'_active_service',None) is None or getattr(self,'_stream_dirty',False):
            event(self, 'source-restart' if force else 'source-ensure')
        try:
            return await fresh(self, force=force)
        except Exception as error:
            event(self, 'source-failure-' + type(error).__name__)
            raise

    async def bounded_pli(self):
        now = monotonic()
        if now - getattr(self, '_video_pli_at', float('-inf')) < 2:
            return
        self._video_pli_at = now
        event(self, 'pli-send')
        await send_pli(self)

    async def watchdog(self):
        # Silence alone cannot distinguish a static screen from a dead source.
        # Restart on a terminated receiver, or proven AU progress while a
        # subscriber cannot obtain its required key. Both share the same budget.
        while True:
            await asyncio.sleep(2)
            count = getattr(self, '_rtp_packets_received', 0)
            if count != getattr(self, '_video_packet_count', 0):
                self._video_packet_count = count
                self._video_packet_at = monotonic()
            task = getattr(self, '_active_recv_task', None)
            starved = any(s.needs_key and s.needs_key_since > 0
                and monotonic() - s.needs_key_since > 15
                and self._last_good_au_t > s.needs_key_since + 10
                for s in self._subscribers.values())
            if (self._subscribers and self._active_service is not None
                    and ((task is not None and task.done()) or starved)):
                event(self, 'key-starved-source-progress' if starved else 'receiver-terminated')
                try:
                    await asyncio.wait_for(self._ensure_fresh_stream(force=True), 12)
                except Exception as error:
                    event(self, 'receiver-recovery-' + type(error).__name__)
                    from pymobiledevice3.remote.core_device.screen_stream import _is_tunnel_dead_error
                    if _is_tunnel_dead_error(error):
                        self._reconnect_signal.set()

    server._ensure_fresh_stream = bounded_fresh
    server._send_rtcp_pli = bounded_pli
    server._stall_watchdog = watchdog
