import unittest
from sms_collect import parse_records


class ParseMessagesTests(unittest.TestCase):
    def records(self, *captions):
        return [{'caption': 'Test, Contact, Show Conversation Details, Button'},
                *({'caption': text, 'platform_identifier': 'recycled-id'} for text in captions)]

    def test_link_suffix_does_not_drop_message(self):
        contact, messages, unknown = parse_records(self.records(
            'Your iMessage, Visit https://example.com/a,b, 23:02, Link'))
        self.assertEqual(contact, 'Test, Contact')
        self.assertEqual(messages[0]['text'], 'Visit https://example.com/a,b')
        self.assertEqual(messages[0]['traits'], ['Link'])
        self.assertFalse(unknown)

    def test_image_message_is_preserved_as_attachment(self):
        _, messages, _ = parse_records(self.records(
            'Your iMessage, Includes picture, 23:05, Button, Image'))
        self.assertEqual(messages[0]['kind'], 'attachment')

    def test_repeated_text_and_recycled_ids_preserve_occurrences(self):
        text = 'Test, Contact, Okay, 23:03'
        _, messages, _ = parse_records(self.records(text, text, 'Test, Contact, Next, 23:04'))
        self.assertEqual([m['text'] for m in messages], ['Okay', 'Okay', 'Next'])
        self.assertTrue(all(m['side'] == 'incoming' for m in messages))

    def test_text_unicode_and_internal_time_preserved(self):
        _, messages, _ = parse_records(self.records(
            'Your iMessage, I\u2019m here, 12:00, \U0001f609, 23:03'))
        self.assertEqual(messages[0]['text'], 'I\u2019m here, 12:00, \U0001f609')
        self.assertEqual(messages[0]['time'], '23:03')

    def test_unknown_sender_is_retained_for_review(self):
        _, messages, unknown = parse_records(self.records('Unexpected sender, Hello, 23:03'))
        self.assertFalse(messages)
        self.assertEqual(len(unknown), 1)

    def test_controls_are_not_messages(self):
        _, messages, unknown = parse_records(self.records('Delivered', 'Message, iMessage', 'Send, Button'))
        self.assertFalse(messages)
        self.assertFalse(unknown)


if __name__ == '__main__':
    unittest.main()
