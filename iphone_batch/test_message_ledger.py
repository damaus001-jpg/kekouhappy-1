import json
import tempfile
import unittest
from unittest.mock import patch
from message_ledger import MessageLedger, append_window
from workspace_service import WorkspaceService


def message(text):
    return {'side': 'incoming', 'text': text, 'time': '10:00', 'kind': 'text'}


class LedgerTests(unittest.TestCase):
    def test_append_preserves_repeated_messages(self):
        old = list(map(message, ['A', 'Okay', 'Okay', 'B']))
        merged, aligned = append_window(old, list(map(message, ['Okay', 'Okay', 'B', 'C'])))
        self.assertTrue(aligned)
        self.assertEqual([m['text'] for m in merged], ['A', 'Okay', 'Okay', 'B', 'C'])

    def test_ambiguous_anchor_and_gap_are_rejected(self):
        for old, new in [(['A', 'B'], ['A', 'B', 'A', 'B', 'C']),
                         (['A', 'B'], ['B', 'C']), (['A', 'B'], ['X', 'Y'])]:
            merged, aligned = append_window(list(map(message, old)), list(map(message, new)))
            self.assertFalse(aligned)
            self.assertEqual([m['text'] for m in merged], old)

    def test_ids_survive_restart_and_devices_are_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = MessageLedger(root)
            first = ledger.commit('one', '+123', [message('Okay'), message('Okay')], [], True)
            self.assertNotEqual(first['messages'][0]['message_id'], first['messages'][1]['message_id'])
            self.assertIsNone(ledger.load('two', '+123'))
            self.assertIsNone(ledger.load('one', '+124'))
            self.assertEqual(first['messages'], MessageLedger(root).load('one', '+123')['messages'])

    def service(self, root, observations, calls):
        def native(device, action, base, **kwargs):
            calls.append(action)
            value = observations.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        def translator(path):
            output = path.with_name(path.stem + '-translated.json')
            output.write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
            return {'output': str(output), 'messages': 0}
        return WorkspaceService(root, native=native, translator=translator)

    def observation(self, texts, fingerprint='live'):
        return {'device': 'one', 'contact': '+123', 'phone_number': '+123',
                'messages': list(map(message, texts)), 'source': 'native-current',
                'context_fingerprint': fingerprint}

    def test_incremental_read_and_reply_uses_live_context(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            service = self.service(root, [self.observation(['A', 'B']), self.observation(['A', 'B', 'C']),
                                          self.observation(['B', 'C', 'D'], 'latest')], calls)
            with patch('workspace_service.read_snapshot', return_value=None):
                for _ in range(3):
                    result = service.capture('one', 'unused')
            self.assertEqual(calls, ['capture'] * 3)
            history = service.conversation('one', result['conversation_id'])
            self.assertEqual([m['text'] for m in history['messages']], ['A', 'B', 'C', 'D'])
            draft = service.direct_draft('one', result['conversation_id'], 'Hello')
            record = json.loads(service.reply_path(draft['id']).read_text(encoding='utf-8'))
            self.assertEqual(record['context_fingerprint'], 'latest')
            self.assertEqual([m['text'] for m in record['context']], ['B', 'C', 'D'])

    def test_gap_fallback_failure_preserves_every_observation(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            service = self.service(root, [self.observation(['A', 'B']), self.observation(['X', 'Y']),
                                          RuntimeError('scan failed')], calls)
            with patch('workspace_service.read_snapshot', return_value=None), patch.object(service, '_backup', side_effect=RuntimeError('backup failed')):
                service.capture('one', 'unused')
                service.capture('one', 'unused')
            ledger = service.ledger.load('one', '+123')
            self.assertFalse(ledger['overlap_confirmed'])
            self.assertEqual([m['text'] for m in ledger['messages']], ['A', 'B'])
            self.assertEqual([m['text'] for m in ledger['pending_windows'][0]['messages']], ['X', 'Y'])

    def test_database_fallback_rereads_live_context(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            service = self.service(root, [self.observation(['A', 'B']), self.observation(['D', 'E']),
                                          self.observation(['D', 'E']), self.observation(['D', 'E', 'F'], 'after-backup')], calls)
            snapshot = {'messages': list(map(message, ['A', 'B', 'C', 'D', 'E'])), 'snapshot_at': 'now'}
            with patch('workspace_service.read_snapshot', return_value=None), patch.object(service, '_backup', return_value=snapshot) as backup:
                service.capture('one', 'unused')
                result = service.capture('one', 'unused')
            backup.assert_called_once_with('one', '+123')
            self.assertEqual(calls, ['capture', 'capture', 'history', 'capture'])
            ledger = service.ledger.load('one', '+123')
            self.assertEqual([m['text'] for m in ledger['messages']], ['A', 'B', 'C', 'D', 'E', 'F'])
            self.assertTrue(ledger['overlap_confirmed'])
            self.assertEqual(service.conversation('one', result['conversation_id'])['context_fingerprint'], 'after-backup')


if __name__ == '__main__':
    unittest.main()
