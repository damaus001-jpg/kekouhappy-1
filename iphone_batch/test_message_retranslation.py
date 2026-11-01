import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from workspace_service import WorkspaceService


class MessageRetranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'diagnostics').mkdir()
        self.path = self.root/'diagnostics'/'conversation-translated.json'
        self.value = {'device':'phone1','contact':'Alice','messages':[
            {'text':'Hello','kind':'text','side':'incoming','translation_zh':'原译文一'},
            {'text':'Hello','kind':'text','side':'incoming','translation_zh':'原译文二'}]}
        self.path.write_text(json.dumps(self.value), encoding='utf-8')
        self.workspace = WorkspaceService(self.root)
        self.translation = Mock()
        self.translation.translate_texts.return_value = {'translations':['新译文']}

    def test_refresh_only_requested_occurrence_and_persists(self):
        result = self.workspace.retranslate_message('phone1',self.path.stem,1,self.translation)
        self.translation.translate_texts.assert_called_once_with('phone1','Alice',['Hello'],force=True)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual([m['translation_zh'] for m in saved['messages']],['原译文一','新译文'])
        self.assertEqual(result['message_index'],1)

    def test_wrong_phone_and_invalid_indexes_never_call_translation(self):
        with self.assertRaises(ValueError):
            self.workspace.retranslate_message('phone2',self.path.stem,0,self.translation)
        for index in [-1,2,True,None]:
            with self.assertRaises(ValueError):
                self.workspace.retranslate_message('phone1',self.path.stem,index,self.translation)
        self.translation.translate_texts.assert_not_called()

    def test_failed_translation_preserves_saved_text(self):
        self.translation.translate_texts.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            self.workspace.retranslate_message('phone1',self.path.stem,1,self.translation)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')),self.value)

    def test_changed_message_is_not_overwritten(self):
        def change(*args,**kwargs):
            self.value['messages'][1]['text']='Changed'
            self.path.write_text(json.dumps(self.value),encoding='utf-8')
            return {'translations':['Wrong target']}
        self.translation.translate_texts.side_effect=change
        with self.assertRaisesRegex(ValueError,'变化'):
            self.workspace.retranslate_message('phone1',self.path.stem,1,self.translation)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['messages'][1]['translation_zh'],'原译文二')
