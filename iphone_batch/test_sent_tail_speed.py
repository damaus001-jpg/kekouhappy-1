import unittest
from unittest.mock import patch

from bubble_records import parse_bubbles
from native_foreground import read_sent_tail, read_window
from test_native_foreground import Inspector, NUMBER, HEADER


class SentTailSpeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfirmed_watch_stops_at_latest_bubble(self):
        rows = ['Back, Button', HEADER, NUMBER+', Older, 09:00',
                'Your iMessage, Latest, 10:00', 'add, Button', 'Message, iMessage', 'Record audio, Button']
        with patch('native_ui_scan.deserialize_object', side_effect=lambda v: v):
            result = await read_window(Inspector(rows), {'phone_number': NUMBER, 'tail_limit': 1}, tail=True)
        self.assertEqual(result['stop_reason'], 'latest_watch')
        self.assertEqual([m['text'] for m in result['messages']], ['Latest'])

    async def test_expected_body_stops_after_unique_overlap_instead_of_six_messages(self):
        bodies = [NUMBER + f', Earlier {i}, 09:0{i}' for i in range(5)]
        bodies += [NUMBER + ', A, 10:00', 'Your iMessage, B, 10:01']
        history, _ = parse_bubbles([{'caption': c} for c in bodies], NUMBER)
        rows = ['Back, Button', HEADER, 'Text Message • SMS', *bodies,
                'Your iMessage, Hello, 10:02', 'add, Button', 'Message, iMessage', 'Record audio, Button']
        results = []
        with patch('native_foreground.deserialize_object', side_effect=lambda v: v), \
             patch('native_ui_scan.deserialize_object', side_effect=lambda v: v), \
             patch('ax_bottom.deserialize_object', side_effect=lambda v: v):
            for expected in (None, 'Hello'):
                phone = Inspector(rows)
                result = await read_sent_tail(phone, {'phone_number': NUMBER, 'history': history,
                                                       'expected_text': expected})
                self.assertTrue(result['bottom_confirmed'])
                self.assertTrue(result['composer_empty'])
                self.assertEqual(result['messages'][-1]['text'], 'Hello')
                results.append((result, len(phone.moves)))
        self.assertEqual(results[1][0]['stop_reason'], 'verified_send_overlap')
        self.assertEqual(len(results[1][0]['messages']), 3)
        self.assertEqual(len(results[0][0]['messages']), 6)
        self.assertLess(results[1][1], results[0][1])


if __name__ == '__main__':
    unittest.main()
