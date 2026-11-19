"""Cancellable foreground reads, independent of background notification scans."""
from dataclasses import dataclass, field
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from message_archive import conversations
from message_ledger import append_verified_window, key
from pairing_patch import PhoneTrustRequired


class ReadingCancelled(Exception):
    pass


def run_native(root, device, action, base, options, cancelled):
    directory = Path(root)/'workspace'/'foreground'
    directory.mkdir(parents=True, exist_ok=True)
    record = directory/(uuid.uuid4().hex + '.json')
    cancel_record = record.with_suffix('.cancel')
    process = None
    try:
        if cancelled():
            raise ReadingCancelled()
        record.write_text(json.dumps({**options, 'cancel_path': str(cancel_record)}, ensure_ascii=False), encoding='utf-8')
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('native_workspace.py')),
            '--device', device, '--action', action, '--base', base, '--record', str(record)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding='utf-8', creationflags=0x08000000 if sys.platform == 'win32' else 0)
        deadline = time.monotonic() + 70
        while True:
            if cancelled():
                raise ReadingCancelled()
            if time.monotonic() >= deadline:
                raise TimeoutError('自动读取超时，已有历史已保留')
            try:
                output, _ = process.communicate(timeout=.05)
                break
            except subprocess.TimeoutExpired:
                continue
        if cancelled():
            raise ReadingCancelled()
        result = json.loads(output.strip().splitlines()[-1])
        if process.returncode or result.get('error'):
            raise ValueError(result.get('error') or '手机读取未完成')
        return result
    finally:
        if process is not None and process.poll() is None:
            cancel_record.touch()
            try:
                process.communicate(timeout=.3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        record.unlink(missing_ok=True)
        cancel_record.unlink(missing_ok=True)


@dataclass
class ReadingState:
    generation: int
    device: str
    cancelled: threading.Event = field(default_factory=threading.Event)
    probe_consumed: bool = False
    number: str | None = None
    contact: str | None = None
    needs_read: bool = True
    fingerprint: str | None = None
    recover_first: bool = False
    retry_at: float = 0
    verified_at: float = 0
    expand: bool = False
    attempts: int = 0
    unconfirmed_fingerprint: str | None = None


class ForegroundReader:
    def __init__(self, service, eligible, native=None, clock=time.monotonic):
        self.service, self.eligible, self.clock = service, eligible, clock
        self._native_injected = native is not None
        self.native = native or (lambda device, action, base, options, cancelled:
                                run_native(service.root, device, action, base, options, cancelled))
        self.lock = threading.RLock()
        self.states, self.cancelled_generations = {}, {}
        self._session_lock = threading.RLock()
        self._session = None
        self._session_device = None
        self._session_client = None
        self._session_generation = -1

    def _ensure_session(self, client, device, generation, cancelled):
        if self._native_injected:
            return None
        from foreground_ax_session import ForegroundAXSession
        with self._session_lock:
            if cancelled():
                raise ReadingCancelled()
            if self._session is not None and self._session_device == device and self._session_client == client:
                if self._session.thread.is_alive() and not self._session.error:
                    self._session_generation = generation
                    return self._session
                self._close_session_locked()
            self._close_session_locked()
            if cancelled():
                raise ReadingCancelled()
            self._session = ForegroundAXSession(self.service.root, device)
            self._session_device, self._session_client = device, client
            self._session_generation = generation
            if cancelled():
                self._close_session_locked()
                raise ReadingCancelled()
            return self._session

    def _close_session_locked(self, client=None, device=None):
        if self._session is None:
            return
        if client is not None and self._session_client != client:
            return
        if device is not None and self._session_device != device:
            return
        session, self._session = self._session, None
        self._session_device = self._session_client = None
        session.close()

    def release(self, body):
        client, generation = self.identity(body)
        self.cancel(body)
        device = body.get('device')
        with self._session_lock:
            if self._session_generation <= generation:
                self._close_session_locked(client=client, device=device if isinstance(device, str) else None)
        return {'phase': 'released'}

    def close(self):
        with self._session_lock:
            self._close_session_locked()

    def prepare(self, body, device):
        client, generation = self.identity(body)
        try:
            state = self._state(body, device)
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        cancelled = lambda: state.cancelled.is_set() or not self.eligible(device)
        if cancelled():
            return {'phase': 'cancelled'}
        if not self.service.phone_lock.acquire(blocking=False):
            return {'phase': 'busy'}
        operation_lock = self.service.device_lock(device)
        acquired = operation_lock.acquire(blocking=False)
        try:
            if not acquired or not self.eligible(device):
                return {'phase': 'busy'}
            self._ensure_session(client, device, generation, cancelled)
            return {'phase': 'prepared'}
        except PhoneTrustRequired as error:
            return {'phase': 'cancelled'} if cancelled() else {'phase': 'trust_required', 'message': str(error)}
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        except Exception as error:
            if cancelled():
                return {'phase': 'cancelled'}
            return {'phase': 'error', 'message': str(error)}
        finally:
            if acquired:
                operation_lock.release()
            self.service.phone_lock.release()

    @staticmethod
    def identity(body):
        client, generation = body.get('client'), body.get('generation')
        if (not isinstance(client, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', client)
                or type(generation) is not int or not 0 <= generation <= 2**53):
            raise ValueError('自动读取任务标记无效')
        return client, generation

    def cancel(self, body):
        client, generation = self.identity(body)
        with self.lock:
            self.cancelled_generations[client] = max(generation, self.cancelled_generations.get(client, -1))
            state = self.states.get(client)
            if state and state.generation <= generation:
                state.cancelled.set()
            self._trim()
        return {'phase': 'cancelled'}

    def _trim(self):
        while len(self.states) > 32:
            self.states.pop(next(iter(self.states))).cancelled.set()
        while len(self.cancelled_generations) > 64:
            self.cancelled_generations.pop(next(iter(self.cancelled_generations)))

    def _state(self, body, device):
        client, generation = self.identity(body)
        with self.lock:
            previous = self.states.get(client)
            if (generation <= self.cancelled_generations.get(client, -1)
                    or previous and previous.generation > generation):
                raise ReadingCancelled()
            if previous and previous.generation == generation and previous.device != device:
                raise ValueError('自动读取设备标记不一致')
            if previous is None or previous.generation != generation:
                if previous:
                    previous.cancelled.set()
                previous = self.states[client] = ReadingState(generation, device)
            self._trim()
            return previous

    def _records(self, device, number, preferred=None):
        from native_conversation import phone_key
        records = [record for record in conversations(device, self.service.root/'diagnostics')
                   if isinstance(record.get('phone_number') or record.get('contact'), str)
                   and phone_key(record.get('phone_number') or record.get('contact') or '') == number]
        if preferred is None:
            preferred = (self.service.ledger.load(device, number) or {}).get('conversation_id')
        if preferred:
            return [record for record in records if record['id'] == preferred][:1]
        return records[:1]

    def _prior(self, device, number):
        prior = self.service.ledger.load(device, number)
        if prior is not None:
            return prior
        cached = self._records(device, number)
        return {'messages': cached[0]['messages'], 'conversation_id': cached[0]['id']} if cached else None

    def probe(self, body, device, base):
        """Run one of up to three client-scheduled probes for a completed tap."""
        attempt = body.get('probe_attempt', 1)
        if type(attempt) is not int or not 1 <= attempt <= 3:
            raise ValueError('号码识别次数无效')
        options = {'recover_first': attempt > 1}
        try:
            state = self._state(body, device)
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        with self.lock:
            if state.probe_consumed:
                return {'phase': 'awaiting_tap'}
            state.probe_consumed = True
        cancelled = lambda: state.cancelled.is_set() or not self.eligible(device)
        if cancelled():
            return {'phase': 'cancelled'}
        if not self.service.phone_lock.acquire(blocking=False):
            return {'phase': 'busy'}
        operation_lock = self.service.device_lock(device)
        acquired = operation_lock.acquire(blocking=False)
        try:
            if not acquired:
                return {'phase': 'busy'}
            if cancelled():
                raise ReadingCancelled()
            client, generation = self.identity(body)
            if self._native_injected:
                result = self.native(device, 'auto_probe', base, options, cancelled)
            else:
                result = self._ensure_session(client, device, generation, cancelled).call(
                    'auto_probe', options, cancelled)
            if cancelled():
                raise ReadingCancelled()
            if not result.get('found'):
                return {'phase': 'not_found', 'elements_checked': result.get('elements_checked', 0)}
            state.number = result['phone_number']
            state.contact = result.get('contact') or state.number
            state.needs_read = True
            state.expand, state.attempts, state.unconfirmed_fingerprint = False, 0, None
            return {'phase': 'identified', 'phone_number': state.number,
                    'conversations': self._records(device, state.number), 'next_seconds': .3}
        except PhoneTrustRequired as error:
            return {'phase': 'cancelled'} if cancelled() else {'phase': 'trust_required', 'message': str(error)}
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        except Exception as error:
            if cancelled():
                return {'phase': 'cancelled'}
            return {'phase': 'error', 'message': str(error)}
        finally:
            if acquired:
                operation_lock.release()
            self.service.phone_lock.release()

    def verify_sent(self, body, device, base):
        """Read-only confirmation of a new outgoing occurrence after user input."""
        from native_conversation import phone_key
        number = phone_key(body.get('phone_number') or '')
        expected = body.get('expected_text')
        if not number or (expected is not None and not isinstance(expected, str)):
            raise ValueError('发送核验参数无效')
        try:
            state = self._state(body, device)
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        cancelled = lambda: state.cancelled.is_set() or not self.eligible(device)
        if cancelled():
            return {'phase': 'cancelled'}
        if not self.service.phone_lock.acquire(blocking=False):
            return {'phase': 'send_pending'}
        lock = self.service.device_lock(device)
        acquired = lock.acquire(blocking=False)
        try:
            if not acquired:
                return {'phase': 'send_pending'}
            prior = self._prior(device, number)
            history = (prior or {}).get('messages', [])
            options = {'phone_number': number, 'history': history[-80:]}
            client, generation = self.identity(body)
            if self._native_injected:
                result = self.native(device, 'auto_sent_tail', base, options, cancelled)
            else:
                result = self._ensure_session(client, device, generation, cancelled).call(
                    'auto_sent_tail', options, cancelled)
            if cancelled():
                raise ReadingCancelled()
            if result.get('changed') or result.get('phone_number') != number:
                return {'phase': 'send_changed'}
            window = result.get('messages') or []
            merged, aligned = append_verified_window(history, window)
            added = merged[len(history):] if aligned and history else []
            outgoing = [m for m in added if m.get('side') == 'outgoing' and
                        (expected is None or m.get('text') == expected)]
            if (not outgoing or not result.get('composer_empty') or not result.get('bottom_confirmed') or result.get('input_active')
                    or result.get('unclassified') or not result.get('bounded_complete')):
                return {'phase': 'send_pending'}
            with self.lock:
                if cancelled():
                    raise ReadingCancelled()
                saved = self.service._save_visible_capture(device, number,
                    {'phone_number': number, 'contact': result.get('contact') or number},
                    result, prior)
                state.number = number
                state.contact = result.get('contact') or number
                state.needs_read = False
                state.fingerprint = result.get('fingerprint')
                state.verified_at = self.clock()
            if cancelled():
                raise ReadingCancelled()
            return {'phase': 'send_saved', 'phone_number': number, 'after_send': True,
                    'conversations': self._records(device, number, saved['conversation_id'])}
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        except PhoneTrustRequired as error:
            return {'phase': 'trust_required', 'message': str(error)}
        finally:
            if acquired:
                lock.release()
            self.service.phone_lock.release()

    def tick(self, body, device, base):
        try:
            state = self._state(body, device)
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        cancelled = lambda: state.cancelled.is_set() or not self.eligible(device)
        if cancelled():
            return {'phase': 'cancelled'}
        if state.number is None:
            return {'phase': 'awaiting_tap'}
        if not self.service.phone_lock.acquire(blocking=False):
            return {'phase': 'busy', 'next_seconds': 1}
        operation_lock = self.service.device_lock(device)
        acquired = operation_lock.acquire(blocking=False)
        try:
            if not acquired:
                return {'phase': 'busy', 'next_seconds': 1}
            if cancelled():
                raise ReadingCancelled()
            prior = self._prior(device, state.number)
            history = (prior or {}).get('messages', [])
            reading = state.needs_read and self.clock() >= state.retry_at
            action = 'auto_read' if reading else 'auto_tail'
            options = {'phone_number': state.number, 'contact': state.contact or state.number,
                       'history': history[-80:], 'allow_overlap_stop': not state.expand and not bool((prior or {}).get('pending_windows'))}
            client, generation = self.identity(body)
            if self._native_injected:
                result = self.native(device, action, base, options, cancelled)
            else:
                result = self._ensure_session(client, device, generation, cancelled).call(action, options, cancelled)
            if cancelled():
                raise ReadingCancelled()
            if result.get('input_active'):
                return {'phase': 'input_paused', 'phone_number': state.number, 'next_seconds': 2}
            if result.get('changed') or result.get('phone_number') != state.number:
                state.number, state.fingerprint, state.needs_read = None, None, True
                state.retry_at = 0
                return {'phase': 'seeking', 'clear_conversation': True, 'next_seconds': .5}
            messages = result.get('messages') or []
            if not messages:
                return {'phase': 'waiting', 'phone_number': state.number,
                        'message': '当前未读到气泡，等待会话更新', 'next_seconds': 2}
            if not reading:
                merged, aligned = append_verified_window(history, messages)
                if (aligned and merged == history and result.get('bounded_complete')
                        and not result.get('unclassified')):
                    # Only establish a checkpoint against already persisted history.
                    state.fingerprint = result['fingerprint']
                    state.needs_read = False
                    state.attempts = 0
                    repeated = len(set(map(key, messages))) != len(messages)
                    if repeated and self.clock() - state.verified_at >= 15:
                        state.needs_read = True
                    return {'phase': 'waiting', 'phone_number': state.number, 'next_seconds': 2}
                date_refresh = (aligned and len(merged) == len(history) and merged != history
                                and result.get('bounded_complete') and not result.get('unclassified')
                                and bool(result.get('context_fingerprint')))
                if not date_refresh and state.attempts >= 2 and result.get('fingerprint') == state.unconfirmed_fingerprint:
                    # This is an observed unresolved window, not a saved checkpoint.
                    # One expanded retry is enough; wait for a new window or manual action.
                    state.needs_read = False
                    return {'phase': 'unconfirmed', 'phone_number': state.number, 'next_seconds': 2}
                if state.attempts >= 2:
                    state.attempts = 0
                if (result.get('fingerprint') != state.fingerprint or self.clock() - state.verified_at >= 15
                        or result.get('unclassified') or not result.get('bounded_complete')):
                    state.needs_read = True
                if not date_refresh:
                    return {'phase': 'changed' if state.needs_read else 'waiting',
                            'phone_number': state.number, 'next_seconds': 2}
            with self.lock:
                if cancelled():
                    raise ReadingCancelled()
                current = dict(result)
                reason = None if result.get('bounded_complete') else '本轮达到读取上限，衔接尚未确认'
                saved = self.service._save_visible_capture(device, state.number,
                    {'contact': state.number, 'phone_number': state.number}, current, prior, reason)
                # Storage and archive must both succeed before waiting for changes.
                persisted = self.service.ledger.load(device, state.number) or {}
                confirmed = persisted.get('overlap_confirmed') is True
                state.expand = not confirmed
                state.attempts = 0 if confirmed else state.attempts + 1
                state.unconfirmed_fingerprint = None if confirmed else result.get('fingerprint')
                state.needs_read = not confirmed
                if state.attempts >= 2:
                    state.needs_read = False
                state.retry_at = self.clock() + (0 if confirmed else 10)
                state.verified_at = self.clock()
                state.fingerprint = None
            if cancelled():
                raise ReadingCancelled()
            response = {'phase': 'saved' if confirmed else 'unconfirmed', 'phone_number': state.number,
                        'scope': saved['scope'], 'next_seconds': 2}
            if confirmed or not history:
                response['conversations'] = self._records(device, state.number)
            elif (prior or {}).get('conversation_id'):
                records = self._records(device, state.number, prior['conversation_id'])
                if records:
                    response['conversations'] = records
            return response
        except PhoneTrustRequired as error:
            return {'phase': 'cancelled'} if cancelled() else {'phase': 'trust_required', 'message': str(error)}
        except ReadingCancelled:
            return {'phase': 'cancelled'}
        except Exception as error:
            if cancelled():
                return {'phase': 'cancelled'}
            return {'phase': 'error', 'message': str(error), 'next_seconds': 3}
        finally:
            if acquired:
                operation_lock.release()
            self.service.phone_lock.release()
