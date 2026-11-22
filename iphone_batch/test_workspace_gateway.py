"""Real HTTP access checks on an isolated dashboard with zero USB phones."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from workspace_access import HEADER, signed_header

class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0))
            cls.port=reservation.getsockname()[1]
        cls.base=f'http://127.0.0.1:{cls.port}'
        cls.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        cls.process=subprocess.Popen([sys.executable,'-c',
            'import controller; controller.discover=lambda:[]; import dashboard; dashboard.main()',
            '--port',str(cls.port),'--device-map',str(Path(os.environ['LOCALAPPDATA'])/'test-devices.json')],cwd=Path(__file__).parent,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=os.environ.copy(),
            creationflags=0x08000000 if os.name=='nt' else 0)
        end=time.monotonic()+20
        while time.monotonic()<end:
            if cls.process.poll() is not None:raise RuntimeError('Isolated gateway exited')
            try:
                cls.opener.open(cls.base+'/',timeout=.5)
            except urllib.error.HTTPError as error:
                if error.code==403:return
            except OSError:pass
            time.sleep(.1)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        raise RuntimeError('Isolated gateway failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)

    def request(self,path='/',method='GET',auth=False,header=None):
        headers={'User-Agent':'Pikachu-Translator Chrome'}
        if auth:headers[HEADER]=signed_header(method,self.base+path)
        if header:headers[HEADER]=header
        request=urllib.request.Request(self.base+path,headers=headers,method=method,
                                       data=b'{}' if method=='POST' else None)
        try:
            with self.opener.open(request,timeout=3) as response:return response.status,response.read()
        except urllib.error.HTTPError as error:return error.code,error.read()

    def test_browser_and_spoofed_browser_cannot_open_pages_assets_or_api(self):
        for path in ['/','/dashboard.js','/workspace.js','/workspace_theme.js','/api/state','/api/messages?device=13']:
            self.assertEqual(self.request(path)[0],403,path)
        self.assertEqual(self.request('/api/devices/trust','POST')[0],403)

    def test_signed_app_can_open_page_assets_and_state(self):
        self.assertEqual(self.request(auth=True)[0],200)
        self.assertEqual(self.request('/dashboard.js',auth=True)[0],200)
        theme_status,theme_source=self.request('/workspace_theme.js',auth=True)
        self.assertEqual(theme_status,200)
        self.assertIn(b'pikachuWorkspaceTheme',theme_source)
        status,data=self.request('/api/state',auth=True)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['devices'],[])

    def test_signed_headers_cannot_be_reused_or_moved(self):
        header=signed_header('GET',self.base+'/api/state')
        self.assertEqual(self.request('/api/state?tampered',header=header)[0],403)
        self.assertEqual(self.request('/api/state',header=header)[0],200)
        self.assertEqual(self.request('/api/state',header=header)[0],403)

if __name__=='__main__':unittest.main()
