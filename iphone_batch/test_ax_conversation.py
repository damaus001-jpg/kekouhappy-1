import unittest
from unittest.mock import patch

from ax_conversation import capture_conversation
from test_native_foreground import Inspector, NUMBER, HEADER


class ConversationCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfirmed_revisit_stays_outside_display_timeline(self):
        from ax_recheck import parse_caption
        phone = self.phone([NUMBER+', A, 10:00', NUMBER+', B, 10:01'])
        messages = [dict(parse_caption(NUMBER+', '+text+', '+clock, NUMBER)[0], occurrence=3-i)
                    for i, (text, clock) in enumerate((('A','10:00'), ('B','10:01')), 1)]
        async def read(**kwargs):
            reverse = kwargs['reverse']
            return {'summary': {'direction': 'up' if reverse else 'down',
                                'reason': 'top_within_three' if reverse else 'bottom_confirmed',
                                'unresolved_intervals': 0 if reverse else 1},
                    'messages': list(messages) if reverse else messages*2,
                    'node_checks': [], 'interval_checks': [], 'rows': []}
        with patch('ax_conversation.read_pass', read):
            result = await capture_conversation(phone)
        self.assertEqual([m['text'] for m in result['messages']], ['A','B'])
        self.assertEqual(len(result['traversal']['rounds'][1]['messages']), 4)
        self.assertFalse(result['bounded_complete'])

    def phone(self, bodies):
        return Inspector(['Back, Button', HEADER, 'Text Message • SMS',
                          'Today 10:00', *bodies, 'add, Button',
                          'Message, Text Message, SMS', 'Record audio, Button'])

    async def test_complete_two_pass_capture_preserves_two_identical_bubbles(self):
        caption = NUMBER+', Again, 10:00'
        phone = self.phone([caption, caption])
        result = await capture_conversation(phone)
        self.assertTrue(result['bottom_confirmed'])
        self.assertTrue(result['bounded_complete'])
        self.assertEqual(result['read_mode'], 'ax-two-pass')
        self.assertEqual([m['text'] for m in result['messages']], ['Again', 'Again'])
        self.assertEqual([m['date_label'] for m in result['messages']], ['Today 10:00']*2)
        self.assertFalse(phone.monitoring)
        self.assertEqual(result['traversal']['rounds'][0]['summary']['reason'], 'top_within_three')

    async def test_wrong_conversation_rejected_before_reading(self):
        phone = self.phone([NUMBER+', A, 10:00'])
        with patch('ax_conversation.read_pass') as read:
            result = await capture_conversation(phone, {'phone_number': '+12025550124'})
        self.assertTrue(result['changed'])
        read.assert_not_called()
        self.assertFalse(phone.monitoring)

    async def test_failed_pass_preserves_evidence_and_restores_bottom(self):
        phone = self.phone([NUMBER+', A, 10:00'])
        async def failed(**kwargs):
            return {'summary': {'reason': 'event_timeout', 'direction': 'up', 'unresolved_intervals': 1},
                    'messages': [], 'node_checks': [], 'interval_checks': [], 'rows': []}
        with patch('ax_conversation.read_pass', failed):
            result = await capture_conversation(phone)
        self.assertTrue(result['bottom_confirmed'])
        self.assertFalse(result['bounded_complete'])
        self.assertTrue(result['unclassified'])
        self.assertFalse(phone.monitoring)
