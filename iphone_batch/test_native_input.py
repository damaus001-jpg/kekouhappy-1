import io
import json
from types import SimpleNamespace
import unittest
import urllib.error
from native_conversation import NativeConversation


class NativeInputTests(unittest.TestCase):
    def test_input_requests_use_acknowledged_dispatch_routes(self):
        phone=NativeConversation();requests=[]
        def open_request(request,timeout):
            requests.append(request)
            return io.BytesIO(b'{"ok":true}')
        phone.opener=SimpleNamespace(open=open_request)
        for path,expected in [('/touch','/manual-touch'),('/key','/manual-key'),('/clipboard','/clipboard')]:
            self.assertTrue(phone.request('http://127.0.0.1:8080',path,{'example':1})['ok'])
            self.assertEqual(requests[-1].full_url,'http://127.0.0.1:8080'+expected)

    def test_input_error_is_reported_once_without_retry(self):
        phone=NativeConversation();calls=[]
        def fail(request,timeout):
            calls.append(request)
            raise urllib.error.HTTPError(request.full_url,500,'failed',{},io.BytesIO(json.dumps({'error':'dead input channel'}).encode()))
        phone.opener=SimpleNamespace(open=fail)
        with self.assertRaisesRegex(ValueError,'dead input channel'):
            phone.request('http://127.0.0.1:8080','/key',{'usages':[]})
        self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
