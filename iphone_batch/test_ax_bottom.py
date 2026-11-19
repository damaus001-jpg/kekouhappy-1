import time
import unittest
from types import SimpleNamespace
from ax_bottom import reach_bottom
from ax_recheck import inspect_node


CONTACT = '+12025550123'


async def replay(rows, anchor=None):
    items = iter(rows)
    moves = []
    async def move(direction):
        moves.append(direction.name)
        return SimpleNamespace(caption=next(items), platform_identifier='id')
    async def inspect(item, *, deadline):
        return await inspect_node({'caption': item.caption}, CONTACT, occurrence=len(moves))
    result = await reach_bottom(move=move, inspect=inspect, deadline=time.monotonic()+5, anchor=anchor)
    return result, moves


class BottomTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_anchor_requires_latest_message_then_control(self):
        result, moves = await replay(['Record audio, Button','Message, iMessage','add, Button',
                                     'Delivered','Your iMessage, Latest, 17:47','Delivered','add, Button'])
        self.assertTrue(result['confirmed'])
        self.assertEqual(result['latest']['text'], 'Latest')
        self.assertEqual(moves[-2:], ['Next','Next'])

    async def test_body_match_ignores_different_time_but_waits_for_control(self):
        result, _ = await replay(['Message, iMessage','Your iMessage, Latest, 17:47',
                                 'Delivered','Message, iMessage'],
                                {'text':'Latest','time':'00:01','side':'outgoing'})
        self.assertTrue(result['confirmed'])
        self.assertEqual(len(result['checks']),4)

    async def test_arrival_between_anchor_and_composer_becomes_new_bottom(self):
        result, _ = await replay(['Message, iMessage','Your iMessage, Old, 17:47',
                                 CONTACT+', New, 17:48','add, Button'], {'text':'Old'})
        self.assertTrue(result['confirmed'])
        self.assertEqual([m['text'] for m in result['messages']], ['Old','New'])
        self.assertEqual(result['latest']['text'], 'New')

    async def test_partial_nearest_bubble_does_not_fall_back_to_older_message(self):
        result, _ = await replay(['Message, iMessage','Message, unavailable'])
        self.assertFalse(result['confirmed'])
        self.assertEqual(result['reason'],'latest_fields_incomplete')

