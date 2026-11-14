import json
import tempfile
import unittest
from pathlib import Path
from device_policy import load_enabled, load_transport, load_readonly, save_access, input_allowed, permitted


class DevicePolicyTests(unittest.TestCase):
    def test_worker_live_input_policy_locks_readonly_disabled_and_malformed_states(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.json'
            save_access(path,{'one','two'},{'two'})
            self.assertTrue(input_allowed('one',path))
            self.assertFalse(input_allowed('two',path))
            self.assertFalse(input_allowed('off',path))
            path.write_text('{broken',encoding='utf-8')
            self.assertFalse(input_allowed('one',path))
    def test_manual_connection_and_monitor_only_survive_reload_without_changing_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'policy.json'
            path.write_text('{"transport":"userspace","enabled_udids":["one","two"],"extra":7}', encoding='utf-8')
            save_access(path, {'one','two','four'}, {'two'})
            self.assertEqual(load_enabled(path), frozenset(['one','two','four']))
            self.assertEqual(load_readonly(path), frozenset(['two']))
            self.assertEqual(load_transport(path), 'userspace')
            self.assertEqual(json.loads(path.read_text())['extra'], 7)
            save_access(path, {'two','four'}, {'two'})
            self.assertEqual(load_enabled(path), frozenset(['two','four']))
            self.assertEqual(load_readonly(path), frozenset(['two']))

    def test_absent_policy_preserves_existing_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(load_enabled(Path(directory)/'policy.json'))

    def test_explicit_empty_list_disables_all_and_filter_is_stable(self):
        rows = [{'udid':'b'}, {'udid':'a'}, {'udid':'c'}]
        self.assertEqual(permitted(rows, frozenset()), [])
        self.assertEqual(permitted(rows, frozenset(['a','b'])), rows[:2])

    def test_invalid_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'policy.json'
            for data in ({}, {'enabled_udids':None}, {'enabled_udids':['../other']}, []):
                path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_enabled(path)

    def test_saved_local_policy_loads_without_external_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'policy.json'
            path.write_text('{"enabled_udids":["a","b"]}', encoding='utf-8')
            self.assertEqual(load_enabled(path), frozenset(['a','b']))

    def test_transport_is_explicit_and_can_revert_to_tunneld(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'policy.json'
            self.assertEqual(load_transport(path), 'tunneld')
            for value in ('tunneld', 'userspace'):
                path.write_text(json.dumps({'transport':value}), encoding='utf-8')
                self.assertEqual(load_transport(path), value)
            path.write_text('{"transport":"unknown"}', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_transport(path)
