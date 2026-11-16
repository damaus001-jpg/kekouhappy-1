import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch
from foreground_reader import ForegroundReader, ReadingCancelled, run_native
from workspace_service import WorkspaceService
from native_workspace import digest


NUMBER = '+12025550123'


def message(text):
    return {'side': 'incoming', 'text': text, 'time': '10:00', 'kind': 'text'}


def window(texts, **extra):
    return {'phone_number': NUMBER, 'messages': list(map(message, texts)), 'unclassified': [],
            'context_fingerprint': digest(list(map(message, texts))), 'source': 'native-current',
            'fingerprint': '|'.join(texts), 'bounded_complete': True, **extra}


class ForegroundReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = WorkspaceService(self.root)
        self.results, self.calls = [], []
        self.selected, self.clock = 'one', 100
        def native(device, action, base, options, cancelled):
            self.calls.append(action)
            value = self.results.pop(0)
            return value() if callable(value) else value
        self.reader = ForegroundReader(self.service, lambda device: self.selected == device,
                                       native=native, clock=lambda: self.clock)
        self.body = {'client': 'test-client', 'generation': 1}

    def tick(self, result=None, **body):
        if result is not None:
            self.results.append(result)
        return self.reader.tick({**self.body, **body}, 'one', 'http://127.0.0.1:8080')

    def identify(self):
        return self.tick({'found': True, 'phone_number': NUMBER})

    def test_identify_then_read_then_only_append_after_change(self):
        self.assertEqual(self.identify()['phase'], 'identified')
        self.assertIsNone(self.service.ledger.load('one', NUMBER))
        self.assertEqual(self.tick(window(['A', 'B']))['phase'], 'saved')
        self.assertEqual(self.reader.states['test-client'].fingerprint, None)
        self.assertEqual(self.tick(window(['A', 'B']))['phase'], 'waiting')
        self.assertEqual(self.reader.states['test-client'].fingerprint, 'A|B')
        self.assertEqual(self.tick(window(['A', 'B', 'C']))['phase'], 'changed')
        self.assertEqual(self.tick(window(['A', 'B', 'C']))['phase'], 'saved')
        self.assertEqual([m['text'] for m in self.service.ledger.load('one', NUMBER)['messages']], ['A', 'B', 'C'])
        self.assertEqual(self.calls, ['auto_probe', 'auto_read', 'auto_tail', 'auto_tail', 'auto_read'])

    def test_cancel_during_native_read_does_not_archive_and_late_epoch_is_rejected(self):
        self.identify()
        def cancel_during_read():
            self.reader.cancel(self.body)
            return window(['A', 'B'])
        self.assertEqual(self.tick(cancel_during_read)['phase'], 'cancelled')
        self.assertIsNone(self.service.ledger.load('one', NUMBER))
        self.assertEqual(self.tick()['phase'], 'cancelled')
        self.assertEqual(self.tick({'found': True, 'phone_number': NUMBER}, generation=2)['phase'], 'identified')

    def test_selected_device_changed_while_reading_discards_result(self):
        self.identify()
        def switch():
            self.selected = 'two'
            return window(['A', 'B'])
        self.assertEqual(self.tick(switch)['phase'], 'cancelled')
        self.assertIsNone(self.service.ledger.load('one', NUMBER))

    def test_ambiguous_repeated_messages_preserve_history_and_pending_window(self):
        self.service.ledger.commit('one', NUMBER, list(map(message, ['A', 'Okay', 'Okay'])), [], True)
        self.identify()
        self.assertEqual(self.tick(window(['Okay', 'Okay', 'Okay']))['phase'], 'unconfirmed')
        ledger = self.service.ledger.load('one', NUMBER)
        self.assertEqual([m['text'] for m in ledger['messages']], ['A', 'Okay', 'Okay'])
        self.assertEqual(len(ledger['pending_windows']), 1)
        self.assertIsNone(self.reader.states['test-client'].fingerprint)

    def test_storage_failure_does_not_advance_checkpoint(self):
        self.identify()
        with patch.object(self.service, '_save_visible_capture', side_effect=OSError('disk unavailable')):
            self.assertEqual(self.tick(window(['A', 'B']))['phase'], 'error')
        state = self.reader.states['test-client']
        self.assertIsNone(state.fingerprint)
        self.assertTrue(state.needs_read)
        self.assertEqual(self.tick(window(['A', 'B']))['phase'], 'saved')

    def test_phone_draft_pauses_before_any_storage(self):
        self.identify()
        self.assertEqual(self.tick({'phone_number': NUMBER, 'input_active': True})['phase'], 'input_paused')
        self.assertIsNone(self.service.ledger.load('one', NUMBER))

    def test_saved_live_context_remains_compatible_with_explicit_send_preparation(self):
        self.identify()
        result = self.tick(window(['A', 'B']))
        draft = self.service.direct_draft('one', result['conversations'][0]['id'], 'Hello')
        self.assertTrue(draft['id'])
        self.assertEqual(self.calls, ['auto_probe', 'auto_read'])

    def test_unresolved_window_gets_one_expanded_retry_then_waits(self):
        self.service.ledger.commit('one', NUMBER, list(map(message, ['A', 'Okay', 'Okay'])), [], True)
        self.identify()
        self.assertEqual(self.tick(window(['Okay', 'Okay', 'Okay']))['phase'], 'unconfirmed')
        self.clock += 11
        self.assertEqual(self.tick(window(['Okay', 'Okay', 'Okay']))['phase'], 'unconfirmed')
        self.clock += 100
        self.assertEqual(self.tick(window(['Okay', 'Okay', 'Okay']))['phase'], 'unconfirmed')
        self.assertEqual(self.calls.count('auto_read'), 2)
        self.assertEqual(self.calls[-1], 'auto_tail')
        self.assertIsNone(self.reader.states['test-client'].fingerprint)

    def test_number_change_does_not_merge_into_previous_recipient(self):
        self.identify()
        result = self.tick({'changed': True, 'phone_number': '+12025550124'})
        self.assertTrue(result['clear_conversation'])
        self.assertIsNone(self.reader.states['test-client'].number)
        self.assertIsNone(self.service.ledger.load('one', NUMBER))

    def test_manual_operation_lock_prevents_native_access(self):
        with patch.object(self.service, 'phone_lock') as lock:
            lock.acquire.return_value = False
            self.assertEqual(self.tick()['phase'], 'busy')
        self.assertEqual(self.calls, [])

    def test_native_process_is_killed_and_private_job_removed_on_cancel(self):
        process = Mock()
        process.poll.return_value = None
        process.communicate.side_effect = [subprocess.TimeoutExpired('native', .3), ('', '')]
        with patch('foreground_reader.subprocess.Popen', return_value=process), \
                self.assertRaises(ReadingCancelled):
            run_native(self.root, 'one', 'auto_read', 'http://127.0.0.1:8080', {},
                       Mock(side_effect=[False, True]))
        process.kill.assert_called_once()
        self.assertEqual(list((self.root/'workspace'/'foreground').glob('*.json')), [])
        self.assertEqual(list((self.root/'workspace'/'foreground').glob('*.cancel')), [])


if __name__ == '__main__':
    unittest.main()
