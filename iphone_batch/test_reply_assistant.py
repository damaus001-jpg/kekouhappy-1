import json
from pathlib import Path
import tempfile
import unittest
from reply_assistant import ReplyAssistant, ReplyStore, fingerprint

class Driver:
    def __init__(self):
        self.context={'contact':'Test contact','messages':[{'side':'incoming','text':'Hi','time':'10:00'}]}
        self.sent=[];self.fail=False;self.returned=0
    def select(self,device):pass
    def read_context(self):return self.context
    def send_text(self,text,contact,expected):
        self.sent.append(text)
        if self.fail:raise TimeoutError('after tap')
    def back_to_unread(self):self.returned+=1

class ReplyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'tasks.sqlite3';self.driver=Driver();self.store=ReplyStore(self.path)
        self.assistant=ReplyAssistant(self.driver,self.store)
        self.task={'id':'task1','device':'phone1','status':'ready',**self.driver.context,
            'fingerprint':fingerprint(self.driver.context['messages']),
            'suggestions':[{'text':'A'},{'text':'B'},{'text':'C'}]}
        self.store.save(self.task)
    def test_selected_reply_only_and_duplicate_confirmation_does_not_resend(self):
        self.assistant.send('task1',1)
        self.assertEqual(self.driver.sent,['B']);self.assertEqual(self.driver.returned,1)
        with self.assertRaises(ValueError):self.assistant.send('task1',1)
        self.assertEqual(self.driver.sent,['B'])
    def test_new_incoming_message_blocks_stale_reply(self):
        self.driver.context['messages'].append({'side':'incoming','text':'Wait','time':'10:01'})
        with self.assertRaises(ValueError):self.assistant.send('task1',0)
        self.assertEqual(self.driver.sent,[]);self.assertEqual(self.store.get('task1')['status'],'stale')
    def test_different_contact_blocks_sending(self):
        self.driver.context={**self.driver.context,'contact':'Other contact'}
        with self.assertRaises(ValueError):self.assistant.send('task1',0)
        self.assertEqual(self.driver.sent,[])
    def test_uncertain_send_is_not_retried_or_skipped(self):
        self.driver.fail=True
        with self.assertRaises(ValueError):self.assistant.send('task1',0)
        self.assertEqual(self.store.get('task1')['status'],'send_uncertain')
        with self.assertRaises(ValueError):self.assistant.send('task1',0)
        with self.assertRaises(ValueError):self.assistant.skip('task1')
        self.assertEqual(self.driver.sent,['A']);self.assertEqual(self.driver.returned,0)
    def test_restart_marks_interrupted_sending_uncertain(self):
        self.store.save({**self.task,'status':'sending'})
        recovered=ReplyStore(self.path)
        self.assertEqual(recovered.get('task1')['status'],'send_uncertain')
    def test_automatic_mode_is_off_after_restart(self):
        self.assertFalse(ReplyAssistant(self.driver,ReplyStore(self.path)).automatic)
    def test_invalid_index_does_not_send(self):
        for index in (True,-1,4,'0'):
            with self.assertRaises(ValueError):self.assistant.send('task1',index)
        self.assertEqual(self.driver.sent,[])
    def test_skip_does_not_send(self):
        self.assistant.skip('task1');self.assertEqual(self.driver.sent,[])
        self.assertEqual(self.store.get('task1')['status'],'skipped')

if __name__=='__main__':unittest.main()
