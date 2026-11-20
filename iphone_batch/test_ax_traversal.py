import time
from types import SimpleNamespace
import unittest

from ax_recheck import inspect_node, parse_caption
from ax_traversal import delivery_receipt, focus_row, read_pass


NUMBER = '+12025550123'
HEADER = NUMBER + ', Show Conversation Details, Button'
LATEST = NUMBER + ', Latest, 13:21'


async def replay(captions, reverse, history=None):
    items = iter(captions)
    visits = 0

    async def move(direction):
        caption = next(items, None)
        if caption is None:
            raise TimeoutError()
        return SimpleNamespace(caption=caption, platform_identifier='recycled', spoken_description=caption)

    async def inspect(item, *, deadline):
        nonlocal visits
        visits += 1
        return await inspect_node({'caption': item.caption}, NUMBER, occurrence=visits)

    return await read_pass(reverse=reverse, phone_number=NUMBER, bottom=parse_caption(LATEST, NUMBER)[0],
                           move=move, inspect=inspect, deadline=time.monotonic()+5, history=history)


class TraversalTests(unittest.IsolatedAsyncioTestCase):
    async def test_observed_encrypted_rcs_header_is_a_top_boundary(self):
        result = await replay([LATEST, 'Text Message • RCS \ufffc Encrypted', HEADER], True)
        self.assertEqual(result['summary']['reason'], 'top_within_three')
        self.assertEqual(len(result['messages']), 1)

    async def test_composer_cycle_does_not_append_the_same_bubble_again(self):
        bubble = 'Your Text Message, Are u around tomorrow?, 09:37'
        path = ['Record audio, Button', 'Message, Text Message, SMS', 'add, Button',
                'Sent as SMS', bubble, 'Thu, Oct 15 at 09:37', 'Text Message • SMS, extra hint',
                HEADER, 'Back, Button']
        result = await replay(path * 4, True)
        self.assertEqual(result['summary']['reason'], 'focus_cycle_verified')
        self.assertEqual([m['text'] for m in result['messages']], ['Are u around tomorrow?'])
        self.assertEqual(sum(c['event']['caption'] == bubble for c in result['node_checks']), 1)

    async def test_real_identical_bubbles_inside_one_composer_cycle_are_preserved(self):
        bubble = 'Your Text Message, Same, 09:37'
        path = ['Record audio, Button', 'Message, Text Message, SMS', 'add, Button',
                bubble, bubble, 'Thu, Oct 15 at 09:37', 'Text Message • SMS, extra hint', HEADER, 'Back, Button']
        result = await replay(path * 3, True)
        self.assertEqual(result['summary']['reason'], 'focus_cycle_verified')
        self.assertEqual([m['text'] for m in result['messages']], ['Same', 'Same'])

    async def test_history_checks_after_three_texts_media_does_not_count(self):
        a = 'Your iMessage, A, 13:18'
        photo = 'Your iMessage, Includes picture, 13:19, Button, Image'
        b = 'Your iMessage, B, 13:20'
        history = [parse_caption(c, NUMBER)[0] for c in (a, photo, b, LATEST)]
        result = await replay([LATEST, b, 'Image', photo, a], True, history)
        self.assertEqual(result['summary']['reason'], 'history_overlap_verified')
        self.assertEqual(len(result['rows']), 5)

    async def test_revisit_keeps_triggering_text_and_stops_at_composer(self):
        result = await replay([NUMBER+', A, 12:00', NUMBER+', B, 12:02',
                               'Your iMessage, Revisited, 12:01',
                               'Message, iMessage', NUMBER+', Must not read, 12:03'], False)
        self.assertEqual(result['summary']['reason'], 'interval_boundary_unconfirmed')
        self.assertEqual([m['text'] for m in result['messages']], ['A', 'B', 'Revisited'])
        self.assertEqual(result['interval_checks'][0]['moves'], 1)
        self.assertEqual(result['interval_checks'][0]['status'], 'conversation_boundary')

    async def test_date_rows_group_same_bubbles_in_both_directions(self):
        rows = ['Thu, Oct 8 at 18:33', 'Your iMessage, Hi, 18:33', 'Image',
                'Your iMessage, Includes picture, 18:45', 'Yesterday 17:26', LATEST]
        for reverse in (False, True):
            result = await replay(rows[::-1] if reverse else rows, reverse)
            self.assertEqual([m.get('date_label') for m in result['messages']],
                             [rows[0], rows[0], rows[4]])
            self.assertEqual([m['time'] for m in result['messages']], ['18:33', '18:45', '13:21'])

    async def test_truncated_upward_scan_never_borrows_date_from_newer_bubble(self):
        result = await replay([LATEST, 'Yesterday 17:26', 'Your iMessage, Older, 08:31'], True)
        older, newer = result['messages']
        self.assertNotIn('date_label', older)
        self.assertEqual(newer['date_label'], 'Yesterday 17:26')

    def test_photo_action_without_handle_preserves_caption(self):
        class PhotoAction:
            caption = 'Save photo'
            @property
            def platform_identifier(self):
                raise KeyError('PlatformElementValue_v1')
        self.assertEqual(focus_row(PhotoAction())['caption'], 'Save photo')
        self.assertIsNone(focus_row(PhotoAction())['platform_identifier'])

    def test_read_receipt_is_separate_from_outgoing_message(self):
        self.assertTrue(delivery_receipt('\u200eRead 15:34'))
        self.assertFalse(delivery_receipt('Your iMessage, Read 15:34, 17:47'))

    async def test_incoming_photo_then_outgoing_text_and_photo(self):
        captions = [NUMBER+', Includes picture, 13:17, Button, Image', 'Save photo, Button',
                    'Your Text Message, Between the photos, 13:18',
                    'Your Text Message, Includes picture, 13:19, Button, Image',
                    'Image', 'Message, Button', LATEST, 'add, Button', 'Message, Text Message, SMS']
        result = await replay(captions, False)
        self.assertEqual(result['summary']['reason'], 'bottom_confirmed')
        self.assertEqual([(m['side'], m['kind']) for m in result['messages']], [
            ('incoming', 'attachment'), ('outgoing', 'text'), ('outgoing', 'attachment'), ('incoming', 'text')])
        self.assertEqual(result['messages'][1]['text'], 'Between the photos')
        self.assertGreater(result['summary']['partial_nodes'], 0)
        self.assertFalse(result['summary']['history_complete'])

    async def test_repeat_text_and_early_phone_title_do_not_end_pass(self):
        one = 'Your Text Message, Again, 12:01'
        result = await replay([LATEST, HEADER, one, one, 'Text Message • SMS', 'Image', 'Button', HEADER], True)
        self.assertEqual(result['summary']['reason'], 'top_within_three')
        self.assertEqual([m['text'] for m in result['messages']], ['Again', 'Again', 'Latest'])
        self.assertNotEqual(result['messages'][0]['occurrence'], result['messages'][1]['occurrence'])

    async def test_fourth_element_is_outside_top_window(self):
        result = await replay(['Text Message', 'Image', 'Button', 'Image', HEADER], True)
        self.assertEqual(result['summary']['reason'], 'event_timeout')

    async def test_encrypted_imessage_marker_precedes_matching_number(self):
        result = await replay(['Message, iMessage', HEADER, LATEST, 'iMessage \ufffc Encrypted', HEADER], True)
        self.assertEqual(result['summary']['reason'], 'top_within_three')
        self.assertEqual(result['summary']['elements'], 5)

    async def test_long_run_of_identical_media_controls_and_text_keeps_moving(self):
        captions = ['Image'] * 9 + ['Your Text Message, Again, 13:17'] * 8
        result = await replay(captions + [LATEST, 'Message, Text Message, SMS'], False)
        self.assertEqual(result['summary']['reason'], 'bottom_confirmed')
        self.assertEqual(len(result['messages']), 9)
        self.assertEqual(result['summary']['interval_attempts'], 0)

    async def test_composer_without_latest_is_unconfirmed(self):
        result = await replay([NUMBER+', Older, 12:50', 'Message, iMessage'], False)
        self.assertEqual(result['summary']['reason'], 'bottom_anchor_missing')

    async def test_number_change_stops_before_next_observation(self):
        result = await replay([LATEST, '+12025550124, Show Conversation Details, Button'], True)
        self.assertEqual(result['summary']['reason'], 'conversation_changed')
        self.assertEqual(len(result['node_checks']), 1)
