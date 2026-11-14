from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from owned_viewer_process import stop_tree


class OwnedViewerTests(unittest.TestCase):
    def fixture(self):
        script=Path(__file__).with_name('controller.py').resolve()
        parent,child=Mock(pid=100),Mock(pid=101)
        parent.cmdline.return_value=['python',str(script),'screen','--udid','one']
        child.cmdline.return_value=['python',str(script.with_name('pmd_entry.py')),'serve-web']
        child.name.return_value='python.exe'
        parent.children.return_value=[child]
        return script,parent,child

    def test_only_verified_device_tree_is_suspended_and_stopped(self):
        script,parent,child=self.fixture()
        with patch('owned_viewer_process.psutil.Process',return_value=parent), patch(
                'owned_viewer_process.psutil.wait_procs',return_value=([],[])):
            stop_tree(100,script,'one')
        parent.suspend.assert_called_once()
        child.suspend.assert_called_once()
        parent.terminate.assert_called_once()
        child.terminate.assert_called_once()

    def test_foreign_device_or_child_is_never_terminated(self):
        script,parent,child=self.fixture()
        with patch('owned_viewer_process.psutil.Process',return_value=parent):
            with self.assertRaises(RuntimeError):stop_tree(100,script,'two')
            child.cmdline.return_value=['python',str(script.parent.parent/'other'/'controller.py')]
            with self.assertRaises(RuntimeError):stop_tree(100,script,'one')
        parent.terminate.assert_not_called()
        child.terminate.assert_not_called()
        parent.resume.assert_called_once()
