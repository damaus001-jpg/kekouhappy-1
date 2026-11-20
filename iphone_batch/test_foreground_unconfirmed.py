import tempfile
import unittest
from pathlib import Path

from foreground_reader import ForegroundReader
from native_workspace import digest
from workspace_service import WorkspaceService

NUMBER = '+12025550123'


def observation(texts, *, complete=True, stamp='full'):
    messages = [{'side': 'incoming', 'text': text, 'kind': 'text', 'time': '10:00'} for text in texts]
    return {'phone_number': NUMBER, 'contact': NUMBER, 'messages': messages,
            'context_fingerprint': digest(messages), 'fingerprint': stamp,
            'bounded_complete': complete, 'source': 'native-current',
            'unclassified': [] if complete else [{'reason': 'partial_image'}]}


class UnconfirmedReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = WorkspaceService(Path(self.temp.name))
        self.now = 100
        self.calls = []
        self.responses = []
        def native(device, action, base, options, cancelled):
            self.calls.append(action)
            return self.responses.pop(0)
        self.reader = ForegroundReader(self.service, lambda device: True, native=native, clock=lambda: self.now)
        self.body = {'client': 'test', 'generation': 1}
        self.old = ['Tail A', 'Tail B', 'Tail C']
        self.full = ['Older 1', 'Older 2', 'Older 3', 'Older 4', *self.old]
        self.service._save_visible_capture('one', NUMBER, {'phone_number': NUMBER, 'contact': NUMBER},
                                          observation(self.old), None)
        self.responses.append({'found': True, 'phone_number': NUMBER})
        self.reader.probe(self.body, 'one', 'base')

    def tick(self, value, advance=0):
        self.now += advance
        self.responses.append(value)
        return self.reader.tick(self.body, 'one', 'base')

    def test_unconfirmed_long_read_is_visible_without_overwriting_confirmed_history(self):
        result = self.tick(observation(self.full, complete=False))
        self.assertEqual(result['phase'], 'unconfirmed')
        self.assertEqual(len(result['conversations'][0]['messages']), len(self.full))
        self.assertEqual(len(self.service.ledger.load('one', NUMBER)['messages']), 3)
        self.assertEqual(len(self.reader._records('one', NUMBER)[0]['messages']), len(self.full))

    def test_two_attempts_stop_unchanged_full_reads_even_when_tail_size_and_handles_change(self):
        self.tick(observation(self.full, complete=False))
        result = self.tick(observation(self.old, stamp='short-backoff-tail'), advance=1)
        self.assertEqual(result['phase'], 'unconfirmed')
        self.assertEqual(self.reader.states['test'].attempts, 1)
        self.tick(observation(self.full, complete=False, stamp='second'), advance=10)
        for index in range(8):
            size = 3 if index % 2 else 6
            result = self.tick(observation(self.full[-size:], stamp='recycled-handle-' + str(index)), advance=6)
            self.assertEqual(result['phase'], 'unconfirmed')
        self.assertEqual(self.calls.count('auto_read'), 2)
        result = self.tick(observation([*self.old, 'New arrival'], stamp='new-occurrence'), advance=6)
        self.assertEqual(result['phase'], 'changed')
        self.tick(observation([*self.full, 'New arrival'], complete=False, stamp='new-full'), advance=6)
        self.assertEqual(self.calls.count('auto_read'), 3)

    def test_reentering_unconfirmed_conversation_reuses_saved_long_window(self):
        self.tick(observation(self.full, complete=False))
        self.body = {'client': 'new-client', 'generation': 1}
        self.responses.append({'found': True, 'phone_number': NUMBER})
        result = self.reader.probe(self.body, 'one', 'base')
        self.assertEqual(len(result['conversations'][0]['messages']), len(self.full))
        self.tick(observation(self.old, stamp='new-session-handles'), advance=10)
        self.assertEqual(self.calls.count('auto_read'), 1)

    def test_latest_only_watch_does_not_restart_full_read_without_new_body(self):
        self.tick(observation(self.full, complete=False))
        self.tick(observation(self.full, complete=False), advance=10)
        self.assertEqual(self.tick(observation(self.old[-1:]), advance=10)['phase'], 'unconfirmed')
        self.assertEqual(self.calls.count('auto_read'), 2)
        self.assertEqual(self.tick(observation(['New arrival']), advance=10)['phase'], 'changed')


if __name__ == '__main__':
    unittest.main()
