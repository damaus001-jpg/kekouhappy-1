import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from message_archive import archive_reading
from workspace_service import WorkspaceService

class RemovedTranslationTests(unittest.TestCase):
    def test_retranslation_never_requests_a_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            provider=Mock()
            workspace=WorkspaceService(Path(folder),requester=provider)
            with self.assertRaisesRegex(ValueError,'8070'):
                workspace.retranslate_message('phone','record',0,provider)
            provider.assert_not_called()
            provider.translate_texts.assert_not_called()

    def test_reading_preserves_raw_occurrences_without_translation(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'capture.json'
            value={'device':'phone','contact':'+15550000001','messages':[
                {'message_id':'one','side':'incoming','text':'你好','translation_zh':'old'},
                {'message_id':'two','side':'incoming','text':'你好'}]}
            source.write_text(json.dumps(value),encoding='utf8')
            result=archive_reading(source)
            saved=json.loads(Path(result['output']).read_text(encoding='utf8'))
            self.assertEqual(result['api_requests'],0)
            self.assertFalse(saved['translation_enabled'])
            self.assertEqual([m['text'] for m in saved['messages']],['你好','你好'])
            self.assertEqual([m['message_id'] for m in saved['messages']],['one','two'])
            self.assertNotIn('translation_zh',saved['messages'][0])
            self.assertEqual(json.loads(source.read_text())['messages'][0]['translation_zh'],'old')

if __name__=='__main__':unittest.main()
