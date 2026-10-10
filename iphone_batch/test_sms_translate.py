import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sms_translate import translate_file
from text_translation import TextCache, TextTranslationService


class TranslationFileTests(unittest.TestCase):
    def test_preserves_occurrences_skips_images_escapes_html_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'sms.json'
            original = {'device': 'test-phone', 'contact': '<contact>', 'messages': [
                {'side': 'incoming', 'text': '<Hello>', 'time': '10:00', 'kind': 'text'},
                {'side': 'incoming', 'text': '<Hello>', 'time': '10:01', 'kind': 'text'},
                {'side': 'incoming', 'text': 'Includes picture', 'kind': 'attachment'}]}
            source.write_text(json.dumps(original), encoding='utf-8')
            calls = []
            def request(payload, key):
                calls.append(payload)
                records = json.loads(payload['messages'][1]['content'])['messages']
                return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
                    'translations': [{'id': r['id'], 'text': '你好'} for r in records]})}}]}
            service = TextTranslationService(cache=TextCache(root / 'cache.db'), requester=request)
            with patch('text_translation.load_config', return_value={'api_key': 'test-key', 'model': 'test-model'}):
                first = translate_file(source, service)
                second = translate_file(source, service)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first['messages'], 2)
            self.assertEqual(second['api_requests'], 0)
            self.assertEqual(second['cache_hits'], 2)
            self.assertEqual(json.loads(source.read_text()), original)
            output = json.loads(Path(first['output']).read_text(encoding='utf-8'))
            self.assertEqual(len(output['messages']), 3)
            self.assertNotIn('translation_zh', output['messages'][2])
            page = Path(first['review_page']).read_text(encoding='utf-8')
            self.assertIn('&lt;Hello&gt;', page)
            self.assertIn('&lt;contact&gt;', page)


if __name__ == '__main__':
    unittest.main()
