import unittest
from native_history_reader import collect_history, join_adjacent


def page(texts, number='+12025550123', loading=False):
    return {'scan_complete': True, 'phone_number': number, 'contact': number,
            'messages': [{'side': 'incoming', 'time': '10:00', 'text': text, 'kind': 'text'} for text in texts],
            'bubble_anchors': tuple(texts), 'loading': loading, 'unclassified': []}


class ReaderTests(unittest.IsolatedAsyncioTestCase):
    async def execute(self, pages, **kwargs):
        iterator = iter(pages)
        moves = []
        async def read():
            return next(iterator)
        async def scroll(up, small):
            moves.append((up, small))
        async def sleep(_):
            pass
        result = await collect_history(read, scroll, sleep=sleep, **kwargs)
        return result, moves

    async def test_missing_number_reaches_top_then_reads_overlapping_windows(self):
        top = page(['a', 'b'])
        end = page(['b', 'c'])
        result, moves = await self.execute([page(['b','c'], number=None), top, top, top, top,
                                             end, end, end, end])
        self.assertTrue(result['ui_start_confirmed'])
        self.assertTrue(result['ui_end_confirmed'])
        self.assertTrue(result['ui_history_complete'])
        self.assertFalse(result['history_complete'])
        self.assertEqual([m['text'] for m in result['messages']], ['a','b','c'])
        self.assertEqual(sum(up for up, _ in moves), 4)

    async def test_loading_breaks_stability(self):
        top = page(['a','b'])
        loading = page(['a','b'], loading=True)
        result, moves = await self.execute([top, top, loading, top, top, top, top,
                                             top, top, top])
        self.assertTrue(result['ui_start_confirmed'])
        self.assertEqual(sum(up for up, _ in moves), 6)

    async def test_overlap_gap_never_claims_complete_history(self):
        top = page(['a','b'])
        result, _ = await self.execute([top,top,top,top,page(['x','y'])])
        self.assertFalse(result['ui_history_complete'])
        self.assertFalse(result['history_alignment'])
        self.assertEqual(result['history_stop_reason'], 'ambiguous_or_missing_overlap')
        self.assertIn('读取不完整', result['scope'])

    async def test_repeated_identical_messages_do_not_get_silently_deduplicated(self):
        top = page(['same','same'])
        newer = page(['same','same','last'])
        self.assertIsNone(join_adjacent(top['messages'], newer['messages']))
        result, _ = await self.execute([top,top,top,top,newer])
        self.assertFalse(result['ui_history_complete'])
        self.assertEqual(len(result['history_windows'][-1]['messages']), 3)
        self.assertEqual([m['text'] for m in result['messages']], ['same','same'])

    async def test_phone_change_aborts_instead_of_mixing_conversations(self):
        first = page(['a'])
        with self.assertRaisesRegex(ValueError, '完整手机号发生变化'):
            await self.execute([first, page(['a'], number='+12025550999')])

    async def test_scroll_limit_is_not_an_earliest_message_claim(self):
        result, _ = await self.execute([page(['c']),page(['b']),page(['a'])], max_up=2)
        self.assertFalse(result['ui_start_confirmed'])
        self.assertFalse(result['ui_history_complete'])

    async def test_no_number_never_establishes_boundary(self):
        unknown = page(['a'], number=None)
        with self.assertRaisesRegex(ValueError, '未确认手机号和历史起点'):
            await self.execute([unknown, unknown, unknown, unknown], max_up=3)


if __name__ == '__main__':
    unittest.main()
