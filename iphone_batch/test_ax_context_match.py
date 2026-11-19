import unittest

from ax_context_match import match_context


def full(text, time='12:02', side='incoming'):
    return {'event': {'caption': text}, 'messages': [
        {'text': text, 'time': time, 'side': side, 'kind': 'text'}], 'status': 'complete'}


def partial(text):
    return {'event': {'caption': 'Message, ' + text}, 'messages': [], 'status': 'partial'}


def session(up, down, probe=()):
    def numbered(checks, first):
        return [dict(check, occurrence=first+i) for i, check in enumerate(checks)]
    return [
        {'summary': {'direction': 'up'}, 'node_checks': numbered(reversed(up), 1),
         'interval_checks': []},
        {'summary': {'direction': 'down'}, 'node_checks': numbered(down, 100),
         'interval_checks': [{'probes': [
             {'direction': 'Next', 'check': c} for c in numbered(probe, 200)]}]}
    ]


class ContextTests(unittest.TestCase):
    def test_link_caption_with_wrong_label_uses_verified_neighbor_context(self):
        address = full('201 Ocean Ave, Santa Monica', '14:04', 'outgoing')
        address['messages'][0]['traits'] = ['Link']
        target = partial('201 Ocean Ave, Santa Monica, Link')
        target.update(status='conflict', reasons=['label_conflicts_with_event'])
        result = match_context(session([self.left, target, self.right],
                                       [self.left, address, self.right]))
        self.assertEqual([r['text'] for r in result], ['201 Ocean Ave, Santa Monica'])

    def setUp(self):
        self.left, self.right = full('A'), full('B')
        self.seen = full('same', '12:01', 'outgoing')
        self.source = [self.left, self.seen, self.right]
        self.target = [self.left, partial('same'), self.right]

    def test_opposite_direction_preserves_observed_time_and_target_visit(self):
        result = match_context(session(self.source, self.target))
        self.assertEqual([(r['occurrence'], r['witness_occurrences'], r['time'], r['side'])
                          for r in result], [(101, [2], '12:01', 'outgoing')])

    def test_probe_only_promotes_existing_target(self):
        result = match_context(session([], self.target, self.source))
        self.assertEqual([(r['occurrence'], r['witness_occurrences']) for r in result],
                         [(101, [201])])
        self.assertEqual(match_context(session([], [], self.source)), [])

    def test_duplicate_body_with_different_contexts_keeps_two_occurrences(self):
        source = self.source + [full('C'), full('same', '15:00'), full('D')]
        target = self.target + [full('C'), partial('same'), full('D')]
        result = match_context(session(source, target))
        self.assertEqual([(r['occurrence'], r['time']) for r in result],
                         [(101, '12:01'), (104, '15:00')])

    def test_multiple_candidates_or_conflicting_witness_vetoes_match(self):
        cases = [self.source[:2] + self.source[1:], self.source * 2,
                 [self.left, full('same', '13:00'), self.right],
                 [self.left, full('different'), self.right], list(reversed(self.source))]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(match_context(session(source, self.target, self.source)), [])

    def test_target_must_be_exact_body_without_conflict(self):
        for middle in (partial('Button'), partial('same '), dict(partial('same'), status='conflict')):
            self.assertEqual(match_context(session(self.source, [self.left, middle, self.right])), [])

    def test_missing_adjacent_anchor_or_direction_change_blocks_probe(self):
        self.assertEqual(match_context(session(self.source, self.target[:-1])), [])
        data = session([], self.target, self.source)
        data[1]['interval_checks'][0]['probes'][-1]['direction'] = 'Previous'
        self.assertEqual(match_context(data), [])

    def test_main_path_is_split_at_probe_and_duplicate_claims_rejected(self):
        data = session(self.source, self.target)
        data[1]['node_checks'][-1]['occurrence'] += 1
        self.assertEqual(match_context(data), [])
        data = session(self.source, self.target * 2)
        for check in data[1]['node_checks'][3:]:
            check['occurrence'] += 5
        self.assertEqual(match_context(data), [])

    def test_conversation_switch_rejects_evidence(self):
        data = session(self.source, self.target)
        data[0]['summary']['reason'] = 'conversation_changed'
        with self.assertRaises(ValueError):
            match_context(data)
