import subprocess
import unittest
from unittest.mock import patch

from dashboard import reveal_developer_mode


class DeveloperModeTests(unittest.TestCase):
    @patch('dashboard.subprocess.run')
    @patch('dashboard.controller.discover', return_value=[{'udid': 'selected-phone'}])
    def test_targets_only_selected_phone(self, discover, run):
        run.return_value.returncode = 0
        result = reveal_developer_mode('selected-phone')
        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ['amfi', 'reveal-developer-mode'])
        self.assertEqual(kwargs['env']['PYMOBILEDEVICE3_UDID'], 'selected-phone')
        self.assertEqual(kwargs['env']['PYMOBILEDEVICE3_USBMUX'], '127.0.0.1:27015')
        self.assertEqual(result['device'], 'selected-phone')

    @patch('dashboard.subprocess.run')
    @patch('dashboard.controller.discover', return_value=[])
    def test_disconnected_phone_never_receives_command(self, discover, run):
        with self.assertRaisesRegex(ValueError, '断开'):
            reveal_developer_mode('selected-phone')
        run.assert_not_called()

    @patch('dashboard.subprocess.run')
    @patch('dashboard.controller.discover', return_value=[{'udid': 'selected-phone'}])
    def test_failure_does_not_claim_success(self, discover, run):
        run.return_value.returncode = 1
        with self.assertRaisesRegex(ValueError, '失败'):
            reveal_developer_mode('selected-phone')
        run.assert_called_once()

    @patch('dashboard.subprocess.run', side_effect=subprocess.TimeoutExpired('reveal', 25))
    @patch('dashboard.controller.discover', return_value=[{'udid': 'selected-phone'}])
    def test_timeout_does_not_retry(self, discover, run):
        with self.assertRaises(subprocess.TimeoutExpired):
            reveal_developer_mode('selected-phone')
        run.assert_called_once()
