import tempfile
import unittest
import json
from pathlib import Path

from reading_progress import ReadingProgress, load_progress, visible_messages


class ReadingProgressTests(unittest.TestCase):
    def test_existing_unconfirmed_archive_exposes_recognized_body_without_rewriting(self):
        from message_archive import conversations
        value = {'device': 'test-device', 'contact': '+1234', 'messages': [], 'bounded_complete': False,
                 'incremental': {'overlap_confirmed': False}, 'traversal': {'rounds': [{
                     'summary': {'direction': 'down'}, 'messages': [], 'node_checks': [
                         {'occurrence': 1, 'messages': [], 'event': {'caption': 'Message, Readable body'}}]}]}}
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'old-reading.json'
            path.write_text(json.dumps(value), encoding='utf-8')
            rows = conversations('test-device', root)[0]['messages']
            self.assertEqual(rows[0]['text'], 'Readable body')
            self.assertTrue(rows[0]['reading_pending'])
            self.assertEqual(json.loads(path.read_text())['messages'], [])

    def test_partial_body_is_visible_without_inventing_sender_or_time(self):
        check = {'occurrence': 1, 'messages': [], 'event': {'caption': 'Message, Identified text'}}
        rows = visible_messages([check])
        self.assertEqual(rows[0]['text'], 'Identified text')
        self.assertEqual(rows[0]['side'], 'unknown')
        self.assertIsNone(rows[0]['time'])
        self.assertTrue(rows[0]['reading_pending'])

    def test_reverse_read_prepends_older_observations_and_preserves_receipt(self):
        newest = {'side': 'outgoing', 'text': 'New', 'time': '10:00', 'kind': 'text', 'occurrence': 2}
        oldest = {'side': 'incoming', 'text': 'Old', 'time': '09:59', 'kind': 'text', 'occurrence': 3}
        checks = [{'occurrence': 1, 'messages': [], 'event': {'caption': 'Not Delivered'}},
                  {'occurrence': 2, 'messages': [newest], 'event': {'caption': 'bubble'}},
                  {'occurrence': 3, 'messages': [oldest], 'event': {'caption': 'bubble'}}]
        rows = visible_messages(checks, reverse=True)
        self.assertEqual([m['text'] for m in rows], ['Old', 'New'])
        self.assertEqual(rows[-1]['bubble_status']['delivery'], 'not_delivered')

    def test_progress_reader_does_not_lose_long_window_on_short_revisit(self):
        with tempfile.TemporaryDirectory() as root:
            publisher = ReadingProgress('test-device', '+1234', '+1234', root=root)
            publisher.publish([{'text': 'A'}, {'text': 'B'}])
            publisher.publish([{'text': 'A'}])
            value = load_progress('test-device', root)
            self.assertEqual(len(value['messages']), 2)
            self.assertEqual(value['phase'], 'reading')
            publisher.publish([{'text': 'A'}, {'text': 'B'}], phase='complete', final=True)
            self.assertEqual(load_progress('test-device', root)['phase'], 'complete')


if __name__ == '__main__':
    unittest.main()
