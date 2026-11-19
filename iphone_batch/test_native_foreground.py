import asyncio
from types import SimpleNamespace
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from pymobiledevice3.services.accessibilityaudit import Direction
from native_foreground import probe_title, read_window, title_number, run_foreground
from bubble_records import parse_bubbles

NUMBER = '+12025550123'
HEADER = NUMBER + ', Show Conversation Details, Button'


class Inspector:
    def __init__(self, captions, silent=False):
        self.items = [SimpleNamespace(platform_identifier=str(i), caption=c) for i, c in enumerate(captions)]
        self._event_queue = asyncio.Queue()
        self.index, self.moves, self.monitoring, self.silent = 0, [], False, silent
    async def set_app_monitoring_enabled(self, value):
        self.monitoring = value
    async def set_monitored_event_type(self):
        pass
    def _extract_event_payload(self, data):
        return data
    async def move_focus(self, direction):
        self.moves.append(direction)
        if self.silent:
            return
        if direction == Direction.First:
            self.index = 0
        elif direction == Direction.Last:
            self.index = len(self.items) - 1
        elif direction == Direction.Previous:
            self.index = (self.index - 1) % len(self.items)
        else:
            self.index = (self.index + 1) % len(self.items)
        self._event_queue.put_nowait(('hostInspectorCurrentElementChanged:', self.items[self.index]))
    async def move_focus_next(self):
        await self.move_focus(Direction.Next)


class NativeForegroundTests(unittest.IsolatedAsyncioTestCase):
    async def test_sent_tail_confirms_empty_composer_and_returns_to_latest(self):
        from native_foreground import read_sent_tail
        service = Inspector(['Back, Button', HEADER, 'Text Message • SMS', 'Today 10:00',
                             NUMBER+', Earlier, 10:00','Your iMessage, Hello, 10:01',
                             'add, Button','Message, iMessage','Record audio, Button'])
        result = await read_sent_tail(service, {'phone_number': NUMBER})
        self.assertTrue(result['composer_empty'])
        self.assertTrue(result['bottom_confirmed'])
        self.assertEqual(result['messages'][-1]['text'],'Hello')
        self.assertEqual(service.items[service.index][0].caption if isinstance(service.items[service.index],list)
                         else service.items[service.index].caption, 'add, Button')
        self.assertFalse(service.monitoring)

    async def asyncSetUp(self):
        self.patches = [patch('native_foreground.deserialize_object', side_effect=lambda value: value),
                        patch('native_ui_scan.deserialize_object', side_effect=lambda value: value)]
        for mock in self.patches:
            mock.start()
            self.addCleanup(mock.stop)

    def test_only_actual_title_matches_english_and_chinese(self):
        self.assertEqual(title_number('+1 (202) 555-0123, Show Conversation Details, Button, Double tap for additional contact options'), NUMBER)
        self.assertEqual(title_number('+1 (202) 555-0123, 显示对话详细信息, 按钮'), NUMBER)
        self.assertIsNone(title_number('Call +12025550123, 10:00'))
        self.assertIsNone(title_number(HEADER + ', body text'))

    async def test_probe_never_walks_more_than_three_controls(self):
        service = Inspector(['Back, Button', 'Search, Text Field', 'Other, Button', HEADER])
        result = await probe_title(service)
        self.assertFalse(result['found'])
        self.assertEqual(result['elements_checked'], 3)
        self.assertEqual(len(service.moves), 3)
        self.assertFalse(service.monitoring)

    async def test_missing_ack_does_not_advance_again(self):
        service = Inspector([HEADER], silent=True)
        result = await probe_title(service)
        self.assertEqual(result['reason'], 'timeout')
        self.assertEqual(len(service.moves), 1)
        self.assertFalse(service.monitoring)

    async def test_reverse_read_keeps_photos_duplicates_and_date(self):
        service = Inspector(['Back, Button', HEADER, 'Nov 15, 2026',
            NUMBER + ', Okay, 10:00', NUMBER + ', Okay, 10:00',
            NUMBER + ', Includes picture', 'Message, iMessage'])
        result = await read_window(service, {'phone_number': NUMBER})
        self.assertTrue(result['bounded_complete'])
        self.assertEqual(len(result['messages']), 3)
        self.assertEqual([m['text'] for m in result['messages'][:2]], ['Okay', 'Okay'])
        self.assertEqual(result['messages'][2]['kind'], 'attachment')
        self.assertEqual(result['messages'][0]['date'], '2026-11-15')
        self.assertEqual(result['history_complete'], False)

    async def test_phone_draft_aborts_message_read(self):
        service = Inspector(['Back, Button', HEADER, NUMBER + ', A, 10:00', 'Message, unsent draft'])
        result = await read_window(service, {'phone_number': NUMBER})
        self.assertTrue(result['input_active'])
        self.assertNotIn('messages', result)

    async def test_overlap_waits_for_reread_of_relative_date(self):
        from bubble_records import date_separator
        history = [dict(side='incoming', text=text, kind='text', time='10:00',
                        **date_separator('Today 10:00')) for text in ('A','B')]
        service = Inspector(['Back, Button', HEADER, 'Yesterday 10:00',
                             NUMBER+', A, 10:00', NUMBER+', B, 10:00', 'Message, iMessage'])
        result = await read_window(service, {'phone_number': NUMBER, 'history': history})
        self.assertEqual(result['stop_reason'], 'overlap')
        self.assertEqual([m.get('date_label') for m in result['messages']], ['Yesterday 10:00']*2)

    async def test_link_preview_message_label_does_not_stop_reverse_read(self):
        card = "Message, That's how I keep in touch with my family."
        service = Inspector(['Back, Button', HEADER,
            NUMBER + ', Before the link, 10:00', card, 'Image',
            'Signal Messenger: Speak Freely', 'signal.org',
            NUMBER + ', After the link, 10:01', 'add, Button',
            'Message, Text Message, SMS', 'Record audio, Button'])
        result = await read_window(service, {'phone_number': NUMBER})
        self.assertNotIn('input_active', result)
        self.assertEqual(result['stop_reason'], 'title')
        self.assertEqual([m['text'] for m in result['messages']],
                         ['Before the link', 'After the link'])
        self.assertEqual([r['caption'] for r in result['unclassified']], [card])
        self.assertEqual(result['source'], 'native-foreground')
        self.assertFalse(service.monitoring)

    async def test_send_button_still_pauses_after_empty_composer_label(self):
        service = Inspector(['Back, Button', HEADER, NUMBER + ', A, 10:00',
                             'Send, Button', 'Message, iMessage'])
        result = await read_window(service, {'phone_number': NUMBER})
        self.assertTrue(result['input_active'])
        self.assertNotIn('messages', result)

    def test_link_preview_summary_remains_unclassified(self):
        card = {'caption': 'Message, A link preview, 10:00', 'platform_identifier': 'card'}
        messages, unknown = parse_bubbles([card], NUMBER)
        self.assertEqual(messages, [])
        self.assertEqual(unknown, [card])

    async def test_formatted_title_matches_incoming_messages_and_send_fingerprint(self):
        from native_workspace import digest
        contact = '+1 (202) 555-0123'
        service = Inspector(['Back, Button', contact + ', Show Conversation Details, Button',
                             contact + ', Hello, 10:00', 'Message, iMessage'])
        result = await read_window(service, {'phone_number': NUMBER})
        self.assertEqual(result['messages'][0]['text'], 'Hello')
        self.assertEqual(result['source'], 'native-current')
        self.assertEqual(result['context_fingerprint'], digest(result['messages']))

    async def test_cancel_marker_releases_accessibility_monitoring(self):
        with tempfile.TemporaryDirectory() as directory:
            cancel = Path(directory)/'job.cancel'
            service = Inspector([HEADER], silent=True)
            task = asyncio.create_task(run_foreground(service, 'auto_probe', {'cancel_path': str(cancel)}))
            await asyncio.sleep(.03)
            cancel.touch()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(service.monitoring)

    def test_recycled_ids_do_not_replace_distinct_message_occurrences(self):
        records = [{'caption': NUMBER + ', ' + text + ', 10:00', 'platform_identifier': 'reused'}
                   for text in ['A', 'B', 'A']]
        messages, _ = parse_bubbles(records, NUMBER)
        self.assertEqual([m['text'] for m in messages], ['A', 'B', 'A'])


if __name__ == '__main__':
    unittest.main()
