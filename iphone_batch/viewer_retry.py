"""Avoid repeatedly starting heavy SDK processes for phones needing user setup."""
import hashlib
import threading


class ViewerRetryPolicy:
    def __init__(self):
        self.lock = threading.Lock()
        self.states = {}

    @staticmethod
    def needs_setup(error):
        return any(text in (error or '') for text in (
            '开发者模式未开启', '无法建立手机可信连接',
            'Selected USB devices are not connected'))

    def reset(self, device):
        with self.lock:
            self.states.pop(device, None)

    def should_retry(self, device, generation, error, now):
        with self.lock:
            state = self.states.get(device)
            if state is None or state['generation'] != generation:
                failures = state['failures'] + 1 if state else 1
                jitter = int(hashlib.sha256(device.encode()).hexdigest()[:4], 16) % 13
                state = {'generation': generation, 'failures': failures,
                         'manual': self.needs_setup(error),
                         'due': now + min(30 * 2 ** min(failures - 1, 4), 300) + jitter}
                self.states[device] = state
            return not state['manual'] and now >= state['due']

    def requires_refresh(self, device):
        with self.lock:
            return self.states.get(device, {}).get('manual', False)
