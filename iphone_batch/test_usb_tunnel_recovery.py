import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from controller import ensure_usb_tunnel


class TunnelRecoveryTests(unittest.TestCase):
    def response(self, value):return io.BytesIO(json.dumps(value).encode())

    def test_existing_target_tunnel_is_refreshed_without_touching_others(self):
        opener=Mock()
        opener.open.side_effect=[
            self.response({'phone':[{'interface':'existing'}],'other':[{'interface':'untouched'}]}),
            self.response({}),
            self.response({'address':'fd00::1','port':1234}),
        ]
        with patch('controller.urllib.request.build_opener',return_value=opener),patch('controller.emit'):
            ensure_usb_tunnel('phone')
        self.assertEqual(opener.open.call_count,3)
        cancel=opener.open.call_args_list[1].args[0]
        self.assertEqual(urlsplit(cancel).path,'/cancel')
        self.assertEqual(parse_qs(urlsplit(cancel).query),{'udid':['phone']})
        start=opener.open.call_args_list[2].args[0]
        self.assertEqual(urlsplit(start).path,'/start-tunnel')
        self.assertEqual(parse_qs(urlsplit(start).query),{'udid':['phone'],'connection_type':['usbmux']})

    def test_only_missing_target_is_created(self):
        opener=Mock()
        opener.open.side_effect=[self.response({'other':[{}]}),self.response({'address':'fd00::1','port':1234})]
        with patch('controller.urllib.request.build_opener',return_value=opener),patch('controller.emit'):
            ensure_usb_tunnel('target')
        url=opener.open.call_args.args[0]
        self.assertEqual(urlsplit(url).path,'/start-tunnel')
        self.assertEqual(parse_qs(urlsplit(url).query),{'udid':['target'],'connection_type':['usbmux']})

    def test_failure_does_not_clear_other_tunnels(self):
        opener=Mock();opener.open.side_effect=OSError('connection refused')
        with patch('controller.urllib.request.build_opener',return_value=opener):
            with self.assertRaisesRegex(RuntimeError,'USB 隧道'):ensure_usb_tunnel('target')
        self.assertEqual(opener.open.call_count,1)


if __name__=='__main__':unittest.main()
