import json
from pathlib import Path
import tempfile
import unittest

from bubble_status import attach_checks, enrich_saved, parse_status
from bubble_records import parse_bubbles
from message_archive import conversations
from message_ledger import append_verified_window, append_window


CONTACT = '+12025550123'


class BubbleStatusTests(unittest.TestCase):
    def test_all_explicit_receipts(self):
        for raw, code in [('Not Delivered', 'not_delivered'), ('Delivered', 'delivered'),
                          ('Read', 'read'), ('已读 15:34', 'read')]:
            self.assertEqual(parse_status(raw)['delivery'], code)
        self.assertEqual(parse_status('\u200eRead 3:34 PM')['read_time'], '3:34 PM')
        self.assertEqual(parse_status('Sent as SMS')['sending_method'], 'sms')
        self.assertEqual(parse_status('Sent as RCS')['sending_method'], 'rcs')
        self.assertIsNone(parse_status('Text Message • RCS'))
        self.assertIsNone(parse_status('Your iMessage, Read 15:34, 17:47'))

    def test_two_directions_and_failed_button(self):
        rows = ['Your Text Message, Old, 09:41', 'Sent as SMS', 'Today 07:54',
                "Your Text Message, New, 07:54", 'Send failure, Button', 'Not Delivered']
        for reverse in (False, True):
            checks, messages = [], []
            for visit, caption in enumerate(reversed(rows) if reverse else rows, 1):
                parsed, _ = parse_bubbles([{'caption': caption}], CONTACT)
                for message in parsed:
                    message['occurrence'] = visit
                messages.extend(parsed)
                checks.append({'occurrence': visit, 'event': {'caption': caption}})
            attach_checks(checks, messages, reverse=reverse)
            by_text = {m['text']: m for m in messages}
            self.assertEqual(by_text['Old']['bubble_status']['sending_method'], 'sms')
            self.assertEqual(by_text['New']['bubble_status']['delivery'], 'not_delivered')

    def test_tail_receipts_do_not_cross_boundary_or_incoming(self):
        rows = ['Your iMessage, A, 10:00', 'Sent as RCS', 'Read 15:34',
                CONTACT+', Reply, 10:01', 'Delivered', 'Your iMessage, B, 10:02',
                'Today 10:02', 'Not Delivered', 'Your iMessage, C, 10:03',
                'Unrelated control', 'Delivered']
        messages, _ = parse_bubbles([{'caption': c} for c in rows], CONTACT)
        self.assertEqual(messages[0]['bubble_status']['sending_method'], 'rcs')
        self.assertEqual(messages[0]['bubble_status']['read_time'], '15:34')
        self.assertTrue(all('bubble_status' not in m for m in messages[1:]))

    def test_nonconsecutive_checks_do_not_attach(self):
        message = {'occurrence': 1, 'side': 'outgoing'}
        attach_checks([{'occurrence': 1, 'event': {'caption': 'bubble'}},
                       {'occurrence': 3, 'event': {'caption': 'Delivered'}}], [message])
        self.assertNotIn('bubble_status', message)

    def test_status_refresh_preserves_message_identity_and_method(self):
        old = [{'side': 'outgoing', 'text': 'A', 'time': '10:00', 'kind': 'text',
                'message_id': 'stable', 'bubble_status': {'sending_method': 'rcs', 'delivery': 'not_delivered'}}]
        for merge in (append_window, append_verified_window):
            observed = [{**old[0], 'bubble_status': parse_status('Read 15:34')}]
            merged, aligned = merge(old, observed)
            self.assertTrue(aligned)
            self.assertEqual(merged[0]['message_id'], 'stable')
            self.assertEqual(merged[0]['bubble_status']['delivery'], 'read')
            self.assertEqual(merged[0]['bubble_status']['sending_method'], 'rcs')
            self.assertEqual(old[0]['bubble_status']['delivery'], 'not_delivered')
            merged, _ = merge(merged, [{**old[0], 'bubble_status': parse_status('Delivered')}])
            self.assertNotIn('read_time', merged[0]['bubble_status'])

    def test_legacy_saved_traversal_reaches_reading_api(self):
        message = {'occurrence': 1, 'side': 'outgoing', 'element_id': 'one',
                   'text': 'A', 'time': '10:00', 'kind': 'text'}
        value = {'device': 'test', 'contact': CONTACT, 'messages': [dict(message)],
                 'traversal': {'rounds': [{'summary': {'direction': 'down'},
                     'messages': [dict(message)], 'node_checks': [
                         {'occurrence': 1, 'event': {'caption': 'bubble'}},
                         {'occurrence': 2, 'event': {'caption': 'Delivered'}}]}]}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'example-reading.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            result = conversations('test', directory)
            self.assertEqual(result[0]['messages'][0]['bubble_status']['delivery'], 'delivered')
            self.assertNotIn('bubble_status', json.loads(path.read_text())['messages'][0])
        value['messages'].append(dict(message))
        enrich_saved(value)
        self.assertTrue(all('bubble_status' not in m for m in value['messages']))

    def test_second_pass_refresh_preserves_identity(self):
        from native_workspace import merge_history_messages
        old = {'side': 'outgoing', 'text': 'A', 'time': '10:00', 'kind': 'text',
               'message_id': 'stable', 'bubble_status': parse_status('Not Delivered')}
        new = {**old, 'bubble_status': parse_status('Delivered')}
        merged, aligned = merge_history_messages([old], [new])
        self.assertTrue(aligned)
        self.assertEqual(merged[0]['message_id'], 'stable')
        self.assertEqual(merged[0]['bubble_status']['delivery'], 'delivered')
        self.assertEqual(old['bubble_status']['delivery'], 'not_delivered')


if __name__ == '__main__':
    unittest.main()
