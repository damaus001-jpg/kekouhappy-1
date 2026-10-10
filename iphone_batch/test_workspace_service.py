import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from native_workspace import context, unread_records, validate_snapshot, composer_is_empty, reopen_reply_recipient, merge_history_messages
from send_policy import validate_send_text
from workspace_service import WorkspaceService


class WorkspaceTests(unittest.TestCase):
    def test_history_overlap_preserves_identical_occurrences(self):
        def message(text):return {'side':'incoming','text':text,'time':'10:00','kind':'text'}
        first=list(map(message,['A','Okay','Okay','B']))
        second=list(map(message,['Okay','Okay','B','C']))
        merged,aligned=merge_history_messages(first,second)
        self.assertTrue(aligned)
        self.assertEqual([m['text'] for m in merged],['A','Okay','Okay','B','C'])
        shorter,aligned=merge_history_messages(merged,second)
        self.assertTrue(aligned);self.assertEqual(shorter,merged)

    def test_disconnected_history_pages_are_not_silently_joined(self):
        first=[{'side':'incoming','text':'A','time':'10:00','kind':'text'}]
        second=[{**first[0],'text':'Different'}]
        merged,aligned=merge_history_messages(first,second)
        self.assertFalse(aligned);self.assertEqual(merged,first)

    def test_sms_placeholder_is_empty_but_existing_drafts_are_preserved(self):
        self.assertTrue(composer_is_empty(['Message, Text Message, SMS', 'Dictate, Button']))
        self.assertFalse(composer_is_empty(['Message, Hello', 'Send, Button']))
        self.assertFalse(composer_is_empty(['Message, Text Message, SMS', 'Send, Button']))
        self.assertFalse(composer_is_empty(['Messages, Header']))

    def test_virtualized_old_bubbles_may_change_but_latest_messages_must_match(self):
        outgoing={'side':'outgoing','text':'How old are you?','time':'11:09','kind':'text'}
        incoming={'side':'incoming','text':'26!','time':'11:11','kind':'text'}
        record={'context_fingerprint':'before','context':[{'side':'incoming','text':'older','time':'10:00','kind':'text'},outgoing,incoming]}
        current={'context_fingerprint':'after','messages':[outgoing,incoming]}
        validate_snapshot(current,record)
        current['messages']=[outgoing,{**incoming,'text':'New reply'}]
        with self.assertRaises(ValueError):validate_snapshot(current,record)
        current['messages']=[{**outgoing,'text':'Different reply'},incoming]
        with self.assertRaises(ValueError):validate_snapshot(current,record)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'diagnostics').mkdir()
        self.source=self.root/'diagnostics'/'conversation-translated.json'
        self.conversation={'device':'phone1','contact':'+14324663508','phone_number':'+14324663508',
            'source':'native-current','context_fingerprint':'snapshot', 'messages':[
                {'side':'outgoing','text':'I am a doctor','time':'10:00','kind':'text'},
                {'side':'incoming','text':'My name is John. I live in Dallas.','time':'10:01','kind':'text','translation_zh':'我叫 John，住在 Dallas。'}]}
        self.source.write_text(json.dumps(self.conversation),encoding='utf-8')
        self.response={'english':'Good night! 😊','back_translation_zh':'晚安！😊'};self.calls=[]
        def model(payload,key):
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.response)}}]}
        def native(device,action,base,**kwargs):
            self.calls.append(action);return {'status':'sent_verified','delivered':False}
        self.service=WorkspaceService(self.root,requester=model,native=native)
        config=patch('workspace_service.load_config',return_value={'api_key':'test-key','model':'test-model'})
        config.start();self.addCleanup(config.stop)

    def test_translation_persists_context_and_only_one_confirmed_send(self):
        draft=self.service.draft('phone1','conversation-translated','晚安！😊')
        self.assertTrue(draft['sendable']);self.assertEqual(self.calls,[])
        self.service.send('phone1',draft['id'],'unused',True)
        with self.assertRaises(ValueError):self.service.send('phone1',draft['id'],'unused',True)
        self.assertEqual(self.calls,['send'])
        case=json.loads(self.service.reply_path(draft['id']).read_text(encoding='utf-8'))
        self.assertEqual(case['chinese'],'晚安！😊');self.assertEqual(case['status'],'sent_verified')
        self.assertEqual(case['context'],self.service.conversation('phone1','conversation-translated')['messages'])

    def test_no_confirmation_or_wrong_phone_cannot_send(self):
        draft=self.service.draft('phone1','conversation-translated','晚安')
        for device,confirm in [('phone1',False),('phone2',True)]:
            with self.assertRaises(ValueError):self.service.send(device,draft['id'],'unused',confirm)
        self.assertFalse(self.calls)

    def test_verified_send_updates_reading_archive_without_another_phone_action(self):
        draft=self.service.draft('phone1','conversation-translated','晚安！😊')
        outgoing={'side':'outgoing','text':draft['english'],'time':'10:02','kind':'text'}
        after={**self.conversation,'messages':self.conversation['messages']+[outgoing],
               'context_fingerprint':'after-send'}
        def native(device,action,base,**kwargs):
            self.calls.append(action)
            return {'status':'sent_verified','delivered':True,'conversation':after,'sent_message':outgoing}
        self.service.native=native
        result=self.service.send('phone1',draft['id'],'unused',True)
        self.assertEqual(self.calls,['send'])
        saved=result['conversation']
        self.assertEqual(saved['id'],result['conversation_id'])
        self.assertEqual(len(saved['messages']),3)
        self.assertEqual(saved['messages'][-1]['text'],draft['english'])
        self.assertEqual(saved['messages'][-1]['translation_zh'],'晚安！😊')
        self.assertEqual(saved['context_fingerprint'],'after-send')
        next_draft=self.service.direct_draft('phone1',saved['id'],'Hello')
        self.assertTrue(next_draft['sendable'])
        case=json.loads(self.service.reply_path(next_draft['id']).read_text(encoding='utf-8'))
        self.assertEqual(case['context'],after['messages'])

    def test_same_text_sent_twice_remains_two_records(self):
        self.service.ledger.commit('phone1',self.conversation['phone_number'],self.conversation['messages'],[],True)
        after_messages=list(self.conversation['messages'])
        def native(device,action,base,record=None,**kwargs):
            value=json.loads(record.read_text(encoding='utf-8'))
            outgoing={'side':'outgoing','text':value['english'],'time':'10:02','kind':'text'}
            after_messages.append(outgoing)
            return {'status':'sent_verified','conversation':{**self.conversation,
                    'messages':list(after_messages),'context_fingerprint':'updated'},'sent_message':outgoing}
        self.service.native=native
        conversation_id='conversation-translated'
        for _ in range(2):
            draft=self.service.direct_draft('phone1',conversation_id,'Okay')
            result=self.service.send('phone1',draft['id'],'unused',True)
            conversation_id=result['conversation_id']
        messages=result['conversation']['messages']
        self.assertEqual(sum(m['text']=='Okay' for m in messages),2)
        self.assertNotEqual(messages[-1]['message_id'],messages[-2]['message_id'])

    def test_reading_update_failure_cannot_make_confirmed_send_retryable(self):
        draft=self.service.direct_draft('phone1','conversation-translated','Hello')
        with patch.object(self.service,'save_sent_conversation',side_effect=OSError('archive unavailable')):
            result=self.service.send('phone1',draft['id'],'unused',True)
        self.assertEqual(result['status'],'sent_verified')
        self.assertIn('archive unavailable',result['reading_error'])
        with self.assertRaises(ValueError):self.service.send('phone1',draft['id'],'unused',True)
        self.assertEqual(self.calls,['send'])

    def test_uncertain_send_is_persisted_and_never_retried(self):
        draft=self.service.direct_draft('phone1','conversation-translated','https://example.com/123')
        def fail(device,action,base,record=None,**kwargs):
            self.calls.append(action);value=json.loads(record.read_text(encoding='utf-8'));value['status']='send_requested'
            self.service.write(record,value);raise TimeoutError('lost reply after send')
        self.service.native=fail
        with self.assertRaises(TimeoutError):self.service.send('phone1',draft['id'],'unused',True)
        self.assertEqual(json.loads(self.service.reply_path(draft['id']).read_text(encoding='utf-8'))['status'],'send_uncertain')
        with self.assertRaises(ValueError):self.service.send('phone1',draft['id'],'unused',True)
        self.assertEqual(self.calls,['send'])

    def test_chinese_model_output_and_tampered_body_are_blocked(self):
        self.response['english']='Good night 晚安'
        with self.assertRaises(ValueError):self.service.draft('phone1','conversation-translated','晚安')
        draft=self.service.direct_draft('phone1','conversation-translated','12345')
        path=self.service.reply_path(draft['id']);value=json.loads(path.read_text(encoding='utf-8'));value['english']='你好'
        self.service.write(path,value)
        with self.assertRaises(ValueError):self.service.send('phone1',draft['id'],'unused',True)
        self.assertFalse(self.calls)

    def test_historical_records_cannot_direct_send(self):
        self.conversation['source']='saved';self.source.write_text(json.dumps(self.conversation))
        draft=self.service.draft('phone1','conversation-translated','晚安')
        self.assertFalse(draft['sendable'])
        with self.assertRaises(ValueError):self.service.direct_draft('phone1','conversation-translated','Hello')

    def test_profile_discards_outgoing_and_invented_evidence_and_caches(self):
        self.response={'fields':[
            {'label':'姓名','value':'John','evidence':[{'id':1,'quote':'My name is John'}]},
            {'label':'工作','value':'医生','evidence':[{'id':0,'quote':'I am a doctor'}]},
            {'label':'年龄','value':'30','evidence':[{'id':1,'quote':'I am 30'}]}]}
        result=self.service.profile('phone1','conversation-translated')
        self.assertEqual([f['label'] for f in result['fields']],['姓名'])
        self.assertTrue(self.service.profile('phone1','conversation-translated')['cached'])

    def test_sending_policy_allows_urls_numbers_emoji_and_blocks_all_han(self):
        for text in ['Hello 😊','https://example.com/123','12345','👍','👨‍👩‍👧‍👦']:
            self.assertEqual(validate_send_text(text),text)
        for text in ['你好','Hello 中','https://example.com/中文','\U00020000','〇','bad\x00text']:
            with self.assertRaises(ValueError):validate_send_text(text)

    def test_native_composer_uses_unique_recipient_and_preserves_raw(self):
        records=[{'caption':'New iMessage, Show Conversation Details, Button'},
                 {'caption':'+1 (432) 466-3508, +14324663508, Button'},
                 {'caption':'+1 (432) 466-3508, Hi, 10:00'},
                 {'caption':'Your Text Message, Hello, 10:01'}]
        value=context(records)
        self.assertEqual(value['phone_number'],'+14324663508')
        self.assertEqual([m['side'] for m in value['messages']],['incoming','outgoing'])
        self.assertEqual(value['raw_elements'],records)
        with self.assertRaises(ValueError):context(records+[{'caption':'+14324663509, Button'}])

    def test_unread_list_separates_named_and_unique_number_rows(self):
        rows=unread_records([{'caption':'Messages, Header'},
            {'caption':'+1 (432) 466-3508, Unread, Hi, 10:00'},
            {'caption':'John, Unread, Hello, 10:01'}])
        self.assertEqual(rows[0]['phone_number'],'+14324663508');self.assertTrue(rows[0]['clickable'])
        self.assertFalse(rows[1]['clickable'])


class RecipientFocusTests(unittest.IsolatedAsyncioTestCase):
    async def test_reopens_exact_number_before_focusing_reply(self):
        phone=AsyncMock()
        record={'phone_number':'+13153602544','context_fingerprint':'same'}
        current={'phone_number':record['phone_number'],'context_fingerprint':'same',
                 'raw_elements':[{'caption':'Message, iMessage'}]}
        pages=[[{'caption':'To:'},{'caption':'Message'},{'caption':'New Message, Show Conversation Details, Button'}],
               [{'caption':'To:, +13153602544'}]]
        with patch('native_workspace.raw_page',AsyncMock(side_effect=pages)), patch('native_workspace.read',AsyncMock(return_value=current)), patch('native_workspace.asyncio.sleep',AsyncMock()):
            self.assertEqual(await reopen_reply_recipient(None,phone,record),current)
        phone.chord.assert_awaited_once_with(0x11)
        phone.paste.assert_awaited_once_with(record['phone_number'])
        self.assertEqual([c.args for c in phone.keys.await_args_list],[([0x28],),([], )])

    async def test_wrong_number_prevents_return_and_reply_input(self):
        phone=AsyncMock()
        pages=[[{'caption':'To:'},{'caption':'Message'},{'caption':'New Message, Show Conversation Details, Button'}],
               [{'caption':'To:, +13153602545'}]]
        with patch('native_workspace.raw_page',AsyncMock(side_effect=pages)), patch('native_workspace.asyncio.sleep',AsyncMock()):
            with self.assertRaises(ValueError):await reopen_reply_recipient(None,phone,{'phone_number':'+13153602544'})
        phone.keys.assert_not_awaited()

    async def test_existing_draft_prevents_reply_input(self):
        phone=AsyncMock()
        record={'phone_number':'+13153602544','context_fingerprint':'same'}
        current={'phone_number':record['phone_number'],'context_fingerprint':'same',
                 'raw_elements':[{'caption':'Message, Existing draft'},{'caption':'Send, Button'}]}
        pages=[[{'caption':'To:'},{'caption':'Message'},{'caption':'New Message, Show Conversation Details, Button'}],
               [{'caption':'To:, +13153602544'}]]
        with patch('native_workspace.raw_page',AsyncMock(side_effect=pages)), patch('native_workspace.read',AsyncMock(return_value=current)), patch('native_workspace.asyncio.sleep',AsyncMock()):
            with self.assertRaises(ValueError):await reopen_reply_recipient(None,phone,record)
        phone.paste.assert_awaited_once_with(record['phone_number'])


if __name__=='__main__':unittest.main()
