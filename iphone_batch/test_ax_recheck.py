import asyncio
import unittest

from ax_recheck import inspect_node, IntervalBudget, unique_tail_pair, PathTransitions, revisit_context

CONTACT = '+1 (732) 673-1539'
PICTURE = CONTACT + ', Includes picture, 13:22'


class RecheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_picture_label_completes_same_occurrence(self):
        calls = []
        async def query():
            calls.append(1)
            return PICTURE
        results = [await inspect_node({'caption': 'Message, Button'}, CONTACT,
                   occurrence=n, query_label=query) for n in (4, 5)]
        self.assertEqual(len(calls), 4)
        self.assertEqual([r['occurrence'] for r in results], [4, 5])
        for result in results:
            self.assertFalse(result['needs_recheck'])
            self.assertEqual(result['source'], 'stable_label')
            self.assertEqual(result['messages'][0]['time'], '13:22')
            self.assertEqual(result['messages'][0]['side'], 'incoming')

    async def test_changed_label_retains_conflict_without_overwriting(self):
        labels = iter([PICTURE, CONTACT + ', Includes picture, 13:23'])
        async def query():
            return next(labels)
        result = await inspect_node({'caption': 'Message, Button'}, CONTACT,
                                    occurrence=1, query_label=query)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['messages'], [])

    async def test_unrelated_label_cannot_fill_partial_body(self):
        async def query():
            return CONTACT + ', Some other body, 13:22'
        result = await inspect_node({'caption': 'Message, original body'}, CONTACT,
                                    occurrence=1, query_label=query)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['messages'], [])

    async def test_body_starting_with_button_is_not_a_generic_control(self):
        async def query():
            return CONTACT + ', unrelated body, 13:22'
        result = await inspect_node({'caption': 'Message, Button me later'}, CONTACT,
                                    occurrence=2, query_label=query)
        self.assertEqual(result['status'], 'conflict')

    async def test_query_timeout_is_bounded_and_leaves_unknown_fields(self):
        async def query():
            await asyncio.sleep(10)
        result = await asyncio.wait_for(inspect_node({'caption': 'Message, Button'}, CONTACT,
            occurrence=1, query_label=query, query_timeout=.01), .2)
        self.assertTrue(result['needs_recheck'])
        self.assertEqual(len(result['label_queries']), 2)
        self.assertEqual(result['messages'], [])

    async def test_composer_and_controls_do_not_query(self):
        async def query():
            self.fail('controls must not be enriched as messages')
        for caption in ('Message, Text Message, SMS', 'Save photo, Button', 'add, Button'):
            result = await inspect_node({'caption': caption}, CONTACT, occurrence=1, query_label=query)
            self.assertFalse(result['needs_recheck'])

    def test_interval_budget_limits_attempts_and_elapsed_time(self):
        clock = [10.0]
        budget = IntervalBudget(clock=lambda: clock[0])
        self.assertEqual(budget.begin(), 22)
        clock[0] = 17
        budget.finish(10)
        self.assertEqual(budget.begin(), 22)
        clock[0] = 23
        budget.finish(17)
        self.assertIsNone(budget.begin())

    def test_repeated_context_pair_is_ambiguous(self):
        def msg(text):
            return {'side': 'incoming', 'time': '13:22', 'kind': 'text', 'text': text}
        self.assertIsNone(unique_tail_pair([msg('a'), msg('b'), msg('a'), msg('b')]))
        self.assertIsNotNone(unique_tail_pair([msg('a'), msg('b'), msg('c')]))

    def test_old_repeated_edge_does_not_flag_new_progress(self):
        path = PathTransitions()
        for key in ('a', 'b', 'a', 'b', 'a', 'b'):
            count = path.observe(key)
        self.assertEqual(count, 3)
        self.assertEqual(path.observe('c'), 1)

    async def test_revisit_a_regressed_focus_prefers_forward_context(self):
        a = {'side': 'incoming', 'text': 'a', 'time': '13:05', 'kind': 'text'}
        b = {**a, 'text': 'b', 'time': '13:08'}
        calls = []
        async def advance(forward, deadline):
            calls.append(forward)
            return [b]
        result = await revisit_context([a, b], [a], advance, IntervalBudget())
        self.assertTrue(result['resolved'])
        self.assertEqual(calls, [True])

    async def test_revisit_does_not_search_forever_if_context_is_missing(self):
        a = {'side': 'incoming', 'text': 'a', 'time': '13:05', 'kind': 'text'}
        b = {**a, 'text': 'b', 'time': '13:08'}
        calls = []
        async def advance(forward, deadline):
            calls.append(forward)
            return []
        result = await revisit_context([a, b], [], advance, IntervalBudget())
        self.assertFalse(result['resolved'])
        self.assertLessEqual(len(calls), 12)

    async def test_path_keeps_incomplete_middle_and_frontier_separate(self):
        a = {'side': 'incoming', 'text': 'a', 'time': '13:05', 'kind': 'text'}
        b = {**a, 'text': 'b', 'time': '13:08'}
        middle = {'text': 'middle', 'kind': 'text'}
        for final, resolved in ((b, True), ({'text': 'b', 'kind': 'text'}, False)):
            steps = iter([[{**a, 'text': 'middle'}], [final]])
            calls = []
            async def advance(forward, deadline):
                calls.append(forward)
                return next(steps)
            result = await revisit_context([a, b], [a], advance, IntervalBudget(),
                                           expected_path=[a, middle, b])
            self.assertEqual(result['resolved'], resolved)
            self.assertTrue(result['position_reacquired'])
            self.assertEqual(calls, [True, True])

    async def test_different_middle_body_cannot_reacquire_path(self):
        a = {'side': 'incoming', 'text': 'a', 'time': '13:05', 'kind': 'text'}
        b = {**a, 'text': 'b', 'time': '13:08'}
        steps = iter([[{**a, 'text': 'different'}], [b], [], [], [], []])
        async def advance(forward, deadline):
            self.assertTrue(forward)
            return next(steps)
        result = await revisit_context([a, b], [a], advance, IntervalBudget(),
                                       expected_path=[a, {'text': 'middle'}, b])
        self.assertFalse(result['resolved'])
        self.assertEqual(result['status'], 'ordered_path_not_reacquired')

    async def test_revisit_timeout_does_not_issue_another_unconfirmed_move(self):
        a = {'side': 'incoming', 'text': 'a', 'time': '13:05', 'kind': 'text'}
        b = {**a, 'text': 'b', 'time': '13:08'}
        calls = []
        async def advance(forward, deadline):
            calls.append(forward)
            await asyncio.sleep(10)
        result = await revisit_context([a, b], [], advance, IntervalBudget(seconds=.01))
        self.assertTrue(result['navigation_uncertain'])
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
