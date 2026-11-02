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
        self.phone=MagicMock();self.phone.paste=AsyncMock();self.phone.keys=AsyncMock();self.phone.chord=AsyncMock()
        self.input={'x':.4,'y':.9};self.send={'x':.86,'y':.9}
        self.points=[]
        self.scroll=AsyncMock()

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
             patch('native_workspace.scroll_history',new=self.scroll), \
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

    async def test_new_manual_request_reuses_proven_unsent_body_without_pasting_twice(self):
        previous={**self.record,'status':'failed',
                  'error':'未定位到唯一可用的手机发送按钮，未执行发送'}
        old=self.path.with_name('b'*32+'.json')
        old.write_text(json.dumps(previous),encoding='utf-8')
        result=await self.execute([self.prepared,self.after])
        self.assertEqual(result['status'],'sent_verified')
        self.phone.paste.assert_not_awaited()
        self.assertEqual(self.points,[self.send])
        self.assertEqual(json.loads(old.read_text())['status'],'failed')

    async def test_owned_body_in_old_viewport_is_located_before_context_is_verified(self):
        self.record['context']=self.before['messages']
        self.path.write_text(json.dumps(self.record),encoding='utf-8')
        previous={**self.record,'status':'failed','prepared_body_verified':True}
        self.path.with_name('b'*32+'.json').write_text(json.dumps(previous),encoding='utf-8')
        older={**self.prepared,'context_fingerprint':'old',
               'messages':[{'side':'incoming','text':'Earlier','kind':'text'}]}
        result=await self.execute([older,self.prepared,self.after])
        self.assertEqual(result['status'],'sent_verified')
        self.scroll.assert_awaited_once_with(self.phone,False)
        self.phone.paste.assert_not_awaited();self.assertEqual(self.points,[self.send])

    async def test_same_phone_body_without_our_failed_preparation_is_preserved(self):
        with self.assertRaisesRegex(ValueError,'草稿'):
            await self.execute([self.prepared])
        self.phone.paste.assert_not_awaited();self.assertEqual(self.points,[])

    async def test_uncertain_previous_attempt_never_authorizes_reusing_phone_body(self):
        previous={**self.record,'status':'send_uncertain','prepared_body_verified':True}
        self.path.with_name('b'*32+'.json').write_text(json.dumps(previous),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'草稿'):
            await self.execute([self.prepared])
        self.phone.paste.assert_not_awaited();self.assertEqual(self.points,[])

    async def test_different_failed_body_does_not_authorize_existing_phone_draft(self):
        previous={**self.record,'status':'failed','english':'Other','prepared_body_verified':True}
        self.path.with_name('b'*32+'.json').write_text(json.dumps(previous),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'草稿'):
            await self.execute([self.prepared])
        self.phone.paste.assert_not_awaited();self.assertEqual(self.points,[])

    async def test_edited_reply_replaces_only_our_verified_unsent_body(self):
        previous={**self.record,'status':'failed','english':'Old body','prepared_body_verified':True}
        self.path.with_name('b'*32+'.json').write_text(json.dumps(previous),encoding='utf-8')
        old_body={**self.before,'raw_elements':[{'caption':'Message, Old body'},{'caption':'Send, Button'}]}
        result=await self.execute([old_body,old_body,self.prepared,self.after])
        self.assertEqual(result['status'],'sent_verified')
        self.phone.chord.assert_awaited_once_with(0x04)
        self.phone.paste.assert_awaited_once_with('Hello')
        self.assertEqual(self.points,[self.input,self.send])

    async def test_body_changed_after_focus_is_preserved_without_replacement(self):
        previous={**self.record,'status':'failed','english':'Old body','prepared_body_verified':True}
        self.path.with_name('b'*32+'.json').write_text(json.dumps(previous),encoding='utf-8')
        old_body={**self.before,'raw_elements':[{'caption':'Message, Old body'},{'caption':'Send, Button'}]}
        changed={**self.before,'raw_elements':[{'caption':'Message, Other draft'},{'caption':'Send, Button'}]}
        with self.assertRaisesRegex(ValueError,'输入内容不一致'):
            await self.execute([old_body,changed])
        self.phone.chord.assert_not_awaited();self.phone.paste.assert_not_awaited()
        self.assertEqual(self.points,[self.input])

    async def test_old_viewport_is_moved_to_latest_before_body_is_pasted(self):
        self.record['context']=self.before['messages']
        self.path.write_text(json.dumps(self.record),encoding='utf-8')
        older={**self.before,'context_fingerprint':'old',
               'messages':[{'side':'incoming','text':'Earlier','kind':'text'}]}
        result=await self.execute([older,self.before,self.prepared,self.after])
        self.assertEqual(result['status'],'sent_verified')
        self.scroll.assert_awaited_once_with(self.phone,False)
        self.phone.paste.assert_awaited_once_with('Hello')
        self.assertEqual(self.points,[self.input,self.send])

    async def test_actual_new_message_still_blocks_without_typing_or_sending(self):
        self.record['context']=self.before['messages']
        self.path.write_text(json.dumps(self.record),encoding='utf-8')
        changed={**self.before,'context_fingerprint':'changed',
                 'messages':[*self.before['messages'],{'side':'incoming','text':'New','kind':'text'}]}
        with self.assertRaisesRegex(ValueError,'最新会话'):
            await self.execute([changed]*4)
        self.assertEqual(self.scroll.await_count,3)
        self.phone.paste.assert_not_awaited();self.assertEqual(self.points,[])
        self.assertEqual(json.loads(self.path.read_text())['status'],'draft')

    async def test_recipient_change_during_latest_lookup_stops_immediately(self):
        older={**self.before,'context_fingerprint':'old'}
        other={**self.before,'phone_number':'+15550000002'}
        with self.assertRaisesRegex(ValueError,'完整号码'):
            await self.execute([older,other])
        self.scroll.assert_awaited_once()
        self.phone.paste.assert_not_awaited();self.assertEqual(self.points,[])


if __name__=='__main__':unittest.main()
