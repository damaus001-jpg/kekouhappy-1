import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from native_workspace import run


class NativeSendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        folder=self.root/'workspace'/'replies';folder.mkdir(parents=True)
        self.path=folder/('a'*32+'.json')
        self.record={'device':'phone-one','phone_number':'+15550000001','english':'Hello',
                     'status':'draft','context_fingerprint':'same'}
        self.path.write_text(json.dumps(self.record),encoding='utf-8')
        self.before={'phone_number':self.record['phone_number'],'context_fingerprint':'same',
                     'messages':[{'side':'incoming','text':'A','kind':'text'}],
                     'raw_elements':[{'caption':'Message, Text Message, SMS'}]}
        self.prepared={**self.before,'raw_elements':[{'caption':'Message, Hello'},{'caption':'Send, Button'}]}
        self.after={**self.before,'messages':[*self.before['messages'],{'side':'outgoing','text':'Hello','kind':'text'}]}
        self.phone=MagicMock();self.phone.paste=AsyncMock();self.phone.keys=AsyncMock()
        self.input={'x':.4,'y':.9};self.send={'x':.86,'y':.9}
        self.points=[]

    async def execute(self,pages):
        audit=AsyncMock();audit.__aenter__.return_value=object()
        async def tap(phone,point):
            self.points.append(point)
            if point==self.send:
                self.assertEqual(json.loads(self.path.read_text())['status'],'send_requested')
        with patch('native_workspace.ROOT',self.root), \
             patch('native_workspace.create_using_usbmux',new=AsyncMock(return_value=AsyncMock())), \
             patch('native_workspace.AccessibilityAudit',return_value=audit), \
             patch('native_workspace.NativeConversation',return_value=self.phone), \
             patch('native_workspace.load_profile',return_value=None), \
             patch('native_workspace.read',new=AsyncMock(side_effect=pages)), \
             patch('native_workspace.input_point',return_value=self.input), \
             patch('native_workspace.send_point',return_value=self.send), \
             patch('native_workspace.tap',new=AsyncMock(side_effect=tap)), \
             patch('native_workspace.asyncio.sleep',new=AsyncMock()):
            return await run(SimpleNamespace(device='phone-one',action='send',base='base',record=str(self.path)))

    async def test_verified_body_activates_send_once_and_confirms_new_bubble(self):
        result=await self.execute([self.before,self.prepared,self.after])
        self.assertEqual(result['status'],'sent_verified')
        self.assertEqual(self.points,[self.input,self.send])
        self.phone.paste.assert_awaited_once_with('Hello')
        self.phone.keys.assert_not_awaited()  # No blind Tab or Return fallback.

    async def test_missing_phone_input_never_activates_send(self):
        with self.assertRaisesRegex(ValueError,'未成功填入'):
            await self.execute([self.before,self.before])
        self.assertEqual(self.points,[self.input])
        self.assertEqual(json.loads(self.path.read_text())['status'],'draft')

    async def test_existing_phone_draft_is_preserved(self):
        self.before['raw_elements']=[{'caption':'Message, Existing draft'},{'caption':'Send, Button'}]
        with self.assertRaisesRegex(ValueError,'草稿'):
            await self.execute([self.before])
        self.assertEqual(self.points,[]);self.phone.paste.assert_not_awaited()

    async def test_missing_post_send_bubble_stays_uncertain_without_second_tap(self):
        with self.assertRaisesRegex(RuntimeError,'发送结果未确认'):
            await self.execute([self.before,self.prepared,self.prepared])
        self.assertEqual(self.points,[self.input,self.send])
        self.assertEqual(json.loads(self.path.read_text())['status'],'send_requested')


if __name__=='__main__':unittest.main()
