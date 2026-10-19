import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import gpt_bridge


class BridgeTests(unittest.TestCase):
    def test_copies_exact_text_and_passes_it_over_stdin(self):
        text='对方：Hello\n我方：你好'
        with patch('gpt_bridge.windows_clipboard') as clipboard, patch('gpt_bridge.shutil.which',return_value='node'), patch('gpt_bridge.subprocess.run',return_value=SimpleNamespace(stdout='{"status":"filled"}')) as run:
            result=gpt_bridge.open_gpt_draft(text)
        clipboard.assert_called_once_with(text,write=True)
        self.assertEqual(json.loads(run.call_args.kwargs['input']),{'text':text})
        self.assertNotIn(text,str(run.call_args.args))
        self.assertEqual(result,{'status':'filled','clipboard_copied':True})

    def test_browser_timeout_preserves_copied_text_without_retry(self):
        with patch('gpt_bridge.windows_clipboard'), patch('gpt_bridge.shutil.which',return_value='node'), patch('gpt_bridge.subprocess.run',side_effect=subprocess.TimeoutExpired('node',55)) as run:
            result=gpt_bridge.open_gpt_draft('example')
        self.assertEqual(result['status'],'browser_error')
        self.assertTrue(result['clipboard_copied']);run.assert_called_once()

    def test_rejects_empty_or_oversized_text_before_touching_clipboard(self):
        with patch('gpt_bridge.windows_clipboard') as clipboard:
            for value in (None,'','x'*(2*1024*1024+1)):
                with self.assertRaises(ValueError):gpt_bridge.open_gpt_draft(value)
        clipboard.assert_not_called()

    def test_overlapping_export_does_not_replace_clipboard(self):
        gpt_bridge._lock.acquire()
        try:
            with patch('gpt_bridge.windows_clipboard') as clipboard:
                with self.assertRaises(ValueError):gpt_bridge.open_gpt_draft('second contact')
            clipboard.assert_not_called()
        finally:gpt_bridge._lock.release()


if __name__=='__main__':unittest.main()
