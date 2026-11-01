import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from message_backup import read_snapshot
from workspace_service import WorkspaceService


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'sms-backup'/'phone1'
        self.folder.mkdir(parents=True)
        (self.folder/'Status.plist').write_bytes(plistlib.dumps({'SnapshotState':'finished'}))
        (self.folder/'Manifest.plist').write_bytes(plistlib.dumps({'IsEncrypted':False}))
        self.source = self.root/'source.db'
        self.db = sqlite3.connect(self.source)
        self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE chat (ROWID INTEGER PRIMARY KEY,chat_identifier TEXT);
            CREATE TABLE message (ROWID INTEGER PRIMARY KEY,guid TEXT,text TEXT,attributedBody BLOB,
                is_from_me INTEGER,is_read INTEGER,date INTEGER,service TEXT,cache_has_attachments INTEGER,
                item_type INTEGER,associated_message_type INTEGER);
            CREATE TABLE chat_message_join (chat_id INTEGER,message_id INTEGER);
            INSERT INTO chat VALUES (1,'+12345678901');''')

    def add(self, number, text, attachment=0, blob=None):
        self.db.execute('INSERT INTO message VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (number,str(number),text,blob,0,1,number*10**9,'SMS',attachment,0,0))
        self.db.execute('INSERT INTO chat_message_join VALUES (1,?)',(number,))
        self.db.commit()

    def copy_payload(self, suffix=''):
        key=hashlib.sha1(('HomeDomain-Library/SMS/sms.db'+suffix).encode()).hexdigest()
        target=self.folder/key[:2]/key
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(Path(str(self.source)+suffix),target)

    def read(self):
        return read_snapshot(self.root,'phone1','+12345678901')

    def test_picture_does_not_stop_later_text_or_merge_repeated_bubbles(self):
        for i,text in enumerate(['Before',None,'After','Okay','Okay'],1):
            self.add(i,text,attachment=int(text is None))
        self.copy_payload()
        result=self.read()
        self.assertTrue(result['history_complete'])
        self.assertEqual(result['record_count'],5)
        self.assertEqual([m['text'] for m in result['messages']],['Before','','After','Okay','Okay'])
        self.assertEqual(result['messages'][1]['kind'],'attachment')
        self.assertEqual(len({m['message_id'] for m in result['messages']}),5)

    def test_wal_only_new_message_is_included(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA wal_autocheckpoint=0')
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.add(1,'New message in WAL')
        self.copy_payload();self.copy_payload('-wal')
        result=self.read()
        self.assertTrue(result['history_complete'])
        self.assertEqual(result['messages'][0]['text'],'New message in WAL')

    def test_phone_number_format_does_not_hide_existing_chat(self):
        self.add(1,'Existing message')
        self.db.execute("UPDATE chat SET chat_identifier='(234) 567-8901'")
        self.db.commit();self.copy_payload()
        self.assertEqual(self.read()['record_count'],1)

    def test_unparsed_body_is_preserved_and_never_claimed_complete(self):
        self.add(1,None,blob=b'unknown-body')
        self.copy_payload()
        with patch('message_backup.attributed_text',side_effect=ValueError('unsupported')):
            result=self.read()
        self.assertFalse(result['history_complete'])
        self.assertEqual(result['decode_errors'],1)
        self.assertEqual(bytes.fromhex(result['messages'][0]['raw_attributed_body_hex']),b'unknown-body')

    def test_missing_joined_row_is_not_complete(self):
        self.add(1,'Before')
        self.db.execute('INSERT INTO chat_message_join VALUES (1,999)');self.db.commit()
        self.copy_payload()
        with self.assertRaisesRegex(ValueError,'数量不一致'):self.read()

    def test_unfinished_or_encrypted_snapshot_is_rejected(self):
        self.copy_payload()
        (self.folder/'Status.plist').write_bytes(plistlib.dumps({'SnapshotState':'moving'}))
        with self.assertRaisesRegex(ValueError,'尚未完成'):self.read()
        (self.folder/'Status.plist').write_bytes(plistlib.dumps({'SnapshotState':'finished'}))
        (self.folder/'Manifest.plist').write_bytes(plistlib.dumps({'IsEncrypted':True}))
        with self.assertRaisesRegex(ValueError,'已加密'):self.read()


class CompleteCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.identity={'contact':'+12345678901','phone_number':'+12345678901'}
        self.calls=[]
        def native(device,action,base,**kwargs):
            self.calls.append(action)
            if action=='capture':raise ValueError('focus blocked at image')
            return dict(self.identity)
        def translator(path):
            output=path.with_name(path.stem+'-translated.json')
            shutil.copy2(path,output)
            return {'output':str(output)}
        self.service=WorkspaceService(self.root,native=native,translator=translator)
        self.snapshot={'messages':[{'text':text,'kind':'text','side':'incoming'}
                                   for text in ['Before image','After image','Okay','Okay']],
                       'snapshot_at':'now','history_complete':True,'decode_errors':0,'record_count':4}

    def test_manual_capture_uses_fresh_database_even_when_ui_traversal_fails(self):
        with patch.object(self.service,'_backup',return_value=self.snapshot) as backup:
            result=self.service.capture_complete('phone1','base')
        backup.assert_called_once_with('phone1',self.identity['phone_number'])
        self.assertEqual(self.calls,['identify','identify','capture'])
        self.assertTrue(result['history_complete'])
        saved=self.service.conversation('phone1',result['conversation_id'])
        self.assertEqual(len(saved['messages']),4)
        self.assertEqual(saved['source'],'backup-snapshot')
        with self.assertRaises(ValueError):self.service.direct_draft('phone1',saved['id'],'Hello')

    def test_backup_failure_never_falls_back_to_claiming_partial_success(self):
        with patch.object(self.service,'_backup',side_effect=ValueError('device locked')):
            with self.assertRaisesRegex(ValueError,'device locked'):
                self.service.capture_complete('phone1','base')
        self.assertFalse(list((self.root/'diagnostics').glob('*.json')))

    def test_recipient_switch_discards_result(self):
        # Use a deterministic two-header sequence, without reading any bubbles.
        headers=iter([self.identity,{'contact':'other','phone_number':'+10987654321'}])
        self.service.native=lambda *args,**kwargs:next(headers)
        with patch.object(self.service,'_backup',return_value=self.snapshot):
            with self.assertRaisesRegex(ValueError,'会话发生切换'):
                self.service.capture_complete('phone1','base')
        self.assertFalse(list((self.root/'diagnostics').glob('*.json')))

    def test_decode_failure_is_saved_as_incomplete(self):
        self.snapshot.update(history_complete=False,decode_errors=1)
        with patch.object(self.service,'_backup',return_value=self.snapshot):
            result=self.service.capture_complete('phone1','base')
        self.assertFalse(result['history_complete'])
        self.assertIn('完整读取未完成',result['scope'])


if __name__=='__main__':unittest.main()
