import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from message_ledger import append_verified_window
from workspace_service import WorkspaceService


def message(text, **extra):
    return {'side':'incoming', 'text':text, 'kind':'text', **extra}


class OverlapTests(unittest.TestCase):
    def test_known_middle_photo_omitted_by_ax_is_preserved(self):
        old=[message('A'),message('',kind='attachment'),message('B')]
        merged,ok=append_verified_window(old,list(map(message,['A','B','C'])))
        self.assertTrue(ok)
        self.assertEqual([m['text'] for m in merged],['A','','B','C'])
        self.assertFalse(append_verified_window([*old,message('',kind='attachment')],list(map(message,['A','B','C'])))[1])

    def test_picture_representation_and_repeated_occurrences_are_preserved(self):
        old=[message('A'),message('',kind='attachment'),message('Okay'),message('Okay'),message('B')]
        window=[message('Includes picture',kind='attachment'),message('Okay'),message('Okay'),message('B'),message('C')]
        merged,ok=append_verified_window(old,window)
        self.assertTrue(ok)
        self.assertEqual([m['text'] for m in merged],['A','','Okay','Okay','B','C'])

    def test_matching_tail_does_not_hide_an_edited_earlier_visible_message(self):
        old=list(map(message,['A','B','C','D']))
        merged,ok=append_verified_window(old,list(map(message,['Changed','B','C','D','E'])))
        self.assertFalse(ok);self.assertEqual(merged,old)

    def test_ambiguous_repeats_and_missing_overlap_are_rejected(self):
        for old,new in [(['A','B'],['A','B','A','B','C']),
                        (['A','B'],['B','C']),(['A','B'],['X','Y']),
                        (['A','Okay','Okay'],['Okay','Okay','Okay'])]:
            with self.subTest(old=old,new=new):
                self.assertFalse(append_verified_window(list(map(message,old)),list(map(message,new)))[1])

    def test_ax_timestamp_change_requires_database(self):
        old=[message('A',time='10:00'),message('B',time='10:01')]
        new=[message('A',time='11:00'),message('B',time='11:01'),message('C')]
        self.assertFalse(append_verified_window(old,new)[1])


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.contact='+12345678901';self.identity={'contact':self.contact,'phone_number':self.contact}
        self.actions=[];self.translated=[]
        self.current={**self.identity,'device':'one','source':'native-current',
                      'context_fingerprint':'now','messages':[message('A'),message('B'),message('C')]}
        def native(device,action,base,**kwargs):
            self.actions.append(action)
            if action=='identify':return dict(self.identity)
            if isinstance(self.current,Exception):raise self.current
            return self.current
        def translate(path):
            value=json.loads(path.read_text(encoding='utf-8'))
            for item in value['messages']:
                if item['kind']=='text' and not item.get('translation_zh'):
                    self.translated.append(item['text']);item['translation_zh']='译文'+item['text']
            output=path.with_name(path.stem+'-translated.json')
            output.write_text(json.dumps(value),encoding='utf-8')
            return {'output':str(output)}
        self.service=WorkspaceService(self.root,native=native,translator=translate)
        self.snapshot={'history_complete':True,'record_count':2,'decode_errors':0,'snapshot_at':'baseline'}

    def seed(self, baseline=True):
        history=[message(text,message_id='db:'+text,record_source='backup-snapshot',
                         translation_zh='旧译文'+text) for text in ['A','B']]
        return self.service.ledger.commit('one',self.contact,history,[],True,self.snapshot,
                                          baseline_complete=baseline)

    def read(self):return self.service.dispatch('one',{'action':'capture'},'base')

    def fresh(self):return {**self.snapshot,'record_count':3,'messages':list(map(message,['A','B','C']))}

    def test_existing_baseline_appends_only_new_messages_without_backup(self):
        before=self.seed()
        with patch.object(self.service,'_backup',side_effect=AssertionError('must not back up')):
            result=self.read()
        self.assertEqual(self.actions,['identify','capture'])
        self.assertEqual(result['mode'],'incremental');self.assertEqual(result['added'],1)
        self.assertEqual(self.translated,['C'])
        saved=self.service.ledger.load('one',self.contact)
        self.assertEqual([m['text'] for m in saved['messages']],['A','B','C'])
        self.assertEqual([m['message_id'] for m in saved['messages'][:2]],
                         [m['message_id'] for m in before['messages']])
        self.assertTrue(saved['baseline_complete']);self.assertTrue(saved['conversation_id'])
        self.assertFalse(result['history_complete'])  # Incremental is not a fresh DB audit.

    def test_unchanged_second_read_does_no_translation_and_survives_restart(self):
        self.seed();first=self.read();self.translated.clear()
        self.service=WorkspaceService(self.root,native=self.service.native,translator=self.service.translator)
        with patch.object(self.service,'_backup',side_effect=AssertionError('must not back up')):
            result=self.read()
        self.assertEqual(result['added'],0);self.assertEqual(self.translated,[])
        saved=self.service.conversation('one',result['conversation_id'])
        self.assertEqual(saved['messages'][-1]['translation_zh'],'译文C')

    def test_refreshing_one_translation_is_retained_by_next_increment(self):
        self.seed();result=self.read()
        path=self.root/'diagnostics'/(result['conversation_id']+'.json')
        value=json.loads(path.read_text());value['messages'][0]['translation_zh']='重新翻译'
        path.write_text(json.dumps(value),encoding='utf-8')
        result=self.read()
        self.assertEqual(self.service.conversation('one',result['conversation_id'])['messages'][0]['translation_zh'],'重新翻译')

    def test_first_read_and_unverified_partial_history_force_database(self):
        for partial in [False,True]:
            with self.subTest(partial=partial):
                if partial:
                    self.service.ledger.commit('one',self.contact,[message('Partial')],[],True)
                with patch.object(self.service,'_backup',return_value=self.fresh()) as backup:
                    result=self.read()
                backup.assert_called_once();self.assertEqual(result['mode'],'database')
                self.assertTrue(result['history_complete'])

    def test_traversal_failure_automatically_reads_database(self):
        self.seed();self.current=ValueError('event_timeout at photo')
        with patch.object(self.service,'_backup',return_value=self.fresh()) as backup:
            result=self.read()
        backup.assert_called_once();self.assertEqual(result['mode'],'database')
        self.assertEqual(result['message_count'],3)
        self.assertTrue(self.service.ledger.load('one',self.contact)['baseline_complete'])

    def test_gap_or_unclassified_bubble_uses_database(self):
        self.seed();self.current['messages']=[message('X'),message('Y')]
        with patch.object(self.service,'_backup',return_value=self.fresh()) as backup:
            result=self.read()
        backup.assert_called_once();self.assertEqual(result['mode'],'database')
        self.seed();self.current['messages']=list(map(message,['A','B','C']))
        self.current['unclassified']=[{'caption':'unknown'}]
        with patch.object(self.service,'_backup',return_value=self.fresh()) as backup:
            self.read()
        backup.assert_called_once()

    def test_older_viewport_reads_latest_before_requesting_database(self):
        self.seed();self.current['messages']=[message('Old viewport')]
        def native(device,action,base,**kwargs):
            self.actions.append(action)
            if action=='identify':return self.identity
            if action=='latest':return {**self.current,'messages':list(map(message,['A','B','C']))}
            return self.current
        self.service.native=native
        with patch.object(self.service,'_backup',side_effect=AssertionError('unneeded backup')):
            result=self.read()
        self.assertEqual(self.actions,['identify','capture','latest'])
        self.assertEqual(result['added'],1)

    def test_failed_database_keeps_history_and_pending_observation(self):
        before=self.seed();self.current['messages']=[message('X'),message('Y')]
        with patch.object(self.service,'_backup',side_effect=ValueError('locked')):
            with self.assertRaisesRegex(ValueError,'未报为读取完成'):self.read()
        saved=self.service.ledger.load('one',self.contact)
        self.assertEqual(saved['messages'],before['messages'])
        self.assertEqual([m['text'] for m in saved['pending_windows'][-1]['messages']],['X','Y'])
        self.assertFalse(saved['baseline_complete'])
        # The pending gap cannot be bypassed by a later, apparently matching window.
        self.current['messages']=list(map(message,['A','B','C']))
        with patch.object(self.service,'_backup',return_value=self.fresh()) as backup:
            self.read()
        backup.assert_called_once()

    def test_switched_recipient_is_not_merged_or_backed_up(self):
        self.seed();self.current['phone_number']='+10987654321'
        with patch.object(self.service,'_backup',side_effect=AssertionError('wrong recipient')):
            with self.assertRaisesRegex(ValueError,'会话发生切换'):self.read()
        self.assertEqual(len(self.service.ledger.load('one',self.contact)['messages']),2)

    def test_existing_complete_release_baseline_migrates_without_backup(self):
        self.seed(baseline=False)
        with patch.object(self.service,'_backup',side_effect=AssertionError('unneeded backup')):
            self.assertEqual(self.read()['mode'],'incremental')

    def test_forced_full_read_bypasses_incremental(self):
        self.seed()
        with patch.object(self.service,'_backup',return_value=self.fresh()) as backup:
            result=self.service.dispatch('one',{'action':'capture','full':True},'base')
        backup.assert_called_once();self.assertEqual(result['mode'],'database')

    def test_translation_failure_keeps_new_messages_for_next_increment(self):
        self.seed();translate=self.service.translator
        self.service.translator=lambda path: (_ for _ in ()).throw(ValueError('API unavailable'))
        with self.assertRaisesRegex(ValueError,'API unavailable'):self.read()
        self.assertEqual(len(self.service.ledger.load('one',self.contact)['messages']),3)
        self.service.translator=translate
        with patch.object(self.service,'_backup',side_effect=AssertionError('unneeded backup')):
            result=self.read()
        self.assertEqual(result['added'],0)
        self.assertEqual(self.translated,['C'])

    def test_verified_send_preserves_incremental_baseline(self):
        self.seed();previous=self.read()
        outgoing=message('Hello',side='outgoing')
        after={**self.current,'messages':[*self.current['messages'],outgoing]}
        record={'conversation_id':previous['conversation_id'],'phone_number':self.contact,
                'english':'Hello','id':'a'*32,'sent_at':'now','chinese':'你好'}
        self.service.save_sent_conversation('one',record,{'conversation':after,'sent_message':outgoing})
        self.assertTrue(self.service.ledger.load('one',self.contact)['baseline_complete'])
        self.current=after
        with patch.object(self.service,'_backup',side_effect=AssertionError('unneeded backup')):
            result=self.read()
        self.assertEqual(result['added'],0)


if __name__=='__main__':unittest.main()
