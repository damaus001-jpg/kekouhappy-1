import asyncio
from contextlib import asynccontextmanager, redirect_stdout
import io
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch
from media_recovery import reset_media_session, reset_workspace_session
from device_reconnect import reset_phone_session

class MediaRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_initialize_cleanup_order_with_no_input(self):
        events=[];rsd=object()
        async def stop(target):self.assertIs(target,rsd);events.append('stop')
        hid=Mock()
        @asynccontextmanager
        async def session(target):
            self.assertIs(target,rsd);events.append('open')
            try:yield hid
            finally:events.append('close')
        result=await reset_media_session(rsd,stop,session)
        self.assertEqual(events,['stop','open','close','stop'])
        self.assertTrue(result['remote_session_reset'])
        self.assertFalse(result['input_events_sent'])
        self.assertEqual(hid.mock_calls,[])

    async def test_cleanup_failure_does_not_open_another_session(self):
        opened=[]
        @asynccontextmanager
        async def session(_):opened.append(True);yield object()
        with self.assertRaises(ConnectionError):
            await reset_media_session(object(),AsyncMock(side_effect=ConnectionError()),session)
        self.assertEqual(opened,[])

    async def test_final_cleanup_must_be_acknowledged(self):
        @asynccontextmanager
        async def session(_):yield object()
        with self.assertRaises(ConnectionError):
            await reset_media_session(object(),AsyncMock(side_effect=[{},ConnectionError()]),session)

    async def test_cli_returns_one_json_line(self):
        result={'ok':True,'remote_session_reset':True,'input_events_sent':False}
        output=io.StringIO()
        with patch('media_recovery.reset_media_session',AsyncMock(return_value=result)),redirect_stdout(output):
            await reset_workspace_session(object())
        self.assertEqual(len(output.getvalue().splitlines()),1)
        self.assertEqual(json.loads(output.getvalue()),result)

class MediaRecoveryRunnerTests(unittest.TestCase):
    def process(self,value,code=0):
        process=Mock();process.communicate.return_value=(json.dumps(value),'');process.returncode=code
        return process

    def test_targets_only_requested_phone_and_requires_no_input_result(self):
        process=self.process({'ok':True,'remote_session_reset':True,'input_events_sent':False})
        with patch('device_reconnect.subprocess.Popen',return_value=process) as launch:
            self.assertTrue(reset_phone_session({'udid':'phone-one'})['ok'])
        self.assertIn('reset-workspace-session',launch.call_args.args[0])
        self.assertEqual(launch.call_args.kwargs['env']['PYMOBILEDEVICE3_UDID'],'phone-one')
        process.communicate.assert_called_once_with(timeout=28)

    def test_incomplete_cleanup_never_claims_success(self):
        for value in [{'ok':True},{'remote_session_reset':True,'input_events_sent':True}]:
            with patch('device_reconnect.subprocess.Popen',return_value=self.process(value)):
                with self.assertRaises(ValueError):reset_phone_session({'udid':'phone-one'})

if __name__=='__main__':unittest.main()
