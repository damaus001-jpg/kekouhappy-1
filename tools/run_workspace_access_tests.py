"""Run mocked/loopback tests with isolated credentials and no real phone input."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

with tempfile.TemporaryDirectory(prefix='workspace-auth-tests-') as root:
    os.environ['LOCALAPPDATA']=root
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'iphone_batch'))
    suite=unittest.defaultTestLoader.loadTestsFromNames([
        'test_workspace_access','test_workspace_gateway','test_viewer_patch','test_dashboard','test_video_compat','test_device_trust','test_device_reconnect','test_device_registry','test_media_recovery','test_video_idle','test_input_health'])
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
