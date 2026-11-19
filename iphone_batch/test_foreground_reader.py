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
    def test_sent_tail_saves_new_outgoing_then_returns_updated_reading(self):
        self.service.ledger.commit('one', NUMBER, [message('A'), message('B')], [], True)
        result = window(['A', 'B', 'Hello'])
        result['messages'][-1]['side'] = 'outgoing'
        result['composer_empty'] = True
        result['bottom_confirmed'] = True
        result['context_fingerprint'] = digest(result['messages'])
        with patch.object(self.reader, 'native', return_value=result) as native:
            response = self.reader.verify_sent({**self.body, 'phone_number': NUMBER,
                                                'expected_text': 'Hello'}, 'one', 'base')
        self.assertEqual(response['phase'], 'send_saved')
        self.assertTrue(response['after_send'])
        self.assertEqual(native.call_args.args[1], 'auto_sent_tail')
        self.assertEqual(response['conversations'][0]['messages'][-1]['text'], 'Hello')
        self.assertEqual(self.service.ledger.load('one', NUMBER)['messages'][-1]['side'], 'outgoing')

    def test_sent_tail_requires_new_occurrence_and_empty_composer(self):
        history = [message('A'), dict(message('Hello'), side='outgoing')]
        self.service.ledger.commit('one', NUMBER, history, [], True)
        for empty in (False, True):
            result = window(['A','Hello'])
            result['messages'][-1]['side'] = 'outgoing'
            result['composer_empty'] = empty
            result['bottom_confirmed'] = True
            with patch.object(self.reader, 'native', return_value=result):
                response = self.reader.verify_sent({**self.body, 'phone_number': NUMBER,
                    'expected_text': 'Hello'}, 'one', 'base')
            self.assertEqual(response['phase'], 'send_pending')
        result['messages'].append(dict(message('Hello'), side='outgoing'))
        with patch.object(self.reader, 'native', return_value=result):
            response = self.reader.verify_sent({**self.body, 'phone_number': NUMBER,
                'expected_text': 'Hello'}, 'one', 'base')
        self.assertEqual(response['phase'], 'send_saved')
        self.assertEqual(len(self.service.ledger.load('one', NUMBER)['messages']), 3)

    def test_sent_tail_rejects_changed_phone(self):
        with patch.object(self.reader, 'native', return_value={'changed':True,'phone_number':'+12025550124'}):
            result = self.reader.verify_sent({**self.body,'phone_number':NUMBER},'one','base')
        self.assertEqual(result['phase'],'send_changed')
        self.assertIsNone(self.service.ledger.load('one',NUMBER))

    def test_second_click_probe_attempt_recovers_first_focus(self):
        with patch.object(self.reader, 'native', return_value={'found': False}) as native:
            result = self.reader.probe({**self.body, 'probe_attempt': 1}, 'one', 'base')
            self.assertEqual(result['phase'], 'not_found')
            self.assertFalse(native.call_args.args[3]['recover_first'])
        with patch.object(self.reader, 'native', return_value={'found': True, 'phone_number': NUMBER}) as native:
            result = self.reader.probe({**self.body, 'generation': 2, 'probe_attempt': 2}, 'one', 'base')
            self.assertEqual(result['phase'], 'identified')
            self.assertTrue(native.call_args.args[3]['recover_first'])

    def test_probe_attempt_limit_validation(self):
        for attempt in (0, 4, True, '2'):
            with self.assertRaises(ValueError):
                self.reader.probe({**self.body, 'probe_attempt': attempt}, 'one', 'base')

    def test_tail_reread_updates_yesterday_without_new_bubbles(self):
        from bubble_records import date_separator
        self.results.append({'found': True, 'phone_number': NUMBER})
        self.assertEqual(self.reader.probe(self.body, 'one', 'test')['phase'], 'identified')
        def dated(label):
            result = window(['A', 'B'])
            for m in result['messages']:
                m.update(date_separator(label))
            return result
        first = self.tick(dated('Today 09:00'))
        before = self.service.ledger.load('one', NUMBER)['messages']
        second = self.tick(dated('Yesterday 09:00'))
        after = self.service.ledger.load('one', NUMBER)['messages']
        self.assertEqual([m['message_id'] for m in before], [m['message_id'] for m in after])
        self.assertEqual([m['date_label'] for m in after], ['Yesterday 09:00']*2)
        self.assertNotEqual(first['conversations'][0]['id'], second['conversations'][0]['id'])
        self.assertEqual(second['conversations'][0]['messages'][0]['date_label'], 'Yesterday 09:00')
        self.assertEqual(self.tick(dated('Yesterday 09:00'))['phase'], 'waiting')

    def test_rejected_pairing_reported_at_prewarm_and_click(self):
        from pairing_patch import PhoneTrustRequired
        with patch.object(self.reader, '_ensure_session', side_effect=PhoneTrustRequired()):
            prepared = self.reader.prepare(self.body, 'one')
        with patch.object(self.reader, 'native', side_effect=PhoneTrustRequired()):
            probed = self.reader.probe(self.body, 'one', 'test')
        for result in (prepared, probed):
            self.assertEqual(result['phase'], 'trust_required')
            self.assertIn('重新连接此设备', result['message'])

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
