import tempfile
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from text_translation import TextCache, TextTranslationService
from translation import save_config

CONFIG={'api_key':'test-key-not-real','model':'deepseek-flash'}
class TextTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'cache.db'
        self.cache=TextCache(self.path);self.calls=[]
        def requester(payload,key):
            self.calls.append(payload)
            records=json.loads(payload['messages'][1]['content'])['messages']
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'translations':[{'id':item['id'],'text':'translated '+item['text']} for item in records]})}}]}
        self.service=TextTranslationService(cache=self.cache,requester=requester)
        self.config=patch('text_translation.load_config',return_value=CONFIG);self.config.start()
    def tearDown(self):
        self.config.stop();self.temp.cleanup()
    def test_scroll_cache_reuses_text_after_restart(self):
        first=self.service.translate_texts('phone1','Alice',['Hello world'])
        another=TextTranslationService(cache=TextCache(self.path),requester=lambda *args:self.fail('cached text must not call API'))
        second=another.translate_texts('phone1','Alice',['Hello\n world'])
        self.assertEqual(first['api_requests'],1);self.assertEqual(second['api_requests'],0)
        self.assertEqual(second['cache_hits'],1)
    def test_contact_and_phone_cache_isolation(self):
        self.service.translate_texts('phone1','Alice',['Hello'])
        self.assertIsNone(self.cache.get('phone1','Bob','deepseek-flash','Hello'))
        self.assertIsNone(self.cache.get('phone2','Alice','deepseek-flash','Hello'))
    def test_duplicate_text_is_sent_once_as_text_only(self):
        result=self.service.translate_texts('phone1','Alice',['Hello world','Hello\nworld'])
        records=json.loads(self.calls[0]['messages'][1]['content'])['messages']
        self.assertEqual(len(records),1)
        self.assertIsInstance(self.calls[0]['messages'][1]['content'],str)
        self.assertNotIn('image_url',json.dumps(self.calls[0]))
        self.assertEqual(result['translations'][0],result['translations'][1])
    def test_clear_contact_and_clear_all(self):
        for contact in ['Alice','Bob']:
            self.cache.put('phone1',contact,'model','source','translated',self.cache.generation)
        self.cache.clear('phone1','Alice')
        self.assertIsNone(self.cache.get('phone1','Alice','model','source'))
        self.assertEqual(self.cache.count(),1)
        self.cache.clear();self.assertEqual(self.cache.count(),0)
    def test_clear_rejects_old_inflight_cache_writes(self):
        generation=self.cache.generation;self.cache.clear()
        self.assertFalse(self.cache.put('phone','Alice','model','source','old',generation))
        self.assertEqual(self.cache.count(),0)
    def test_incomplete_reply_not_cached(self):
        self.service.requester=lambda *args:{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}
        with self.assertRaises(RuntimeError):self.service.translate_texts('phone','Alice',['source'])
        self.assertEqual(self.cache.count(),0)
    def test_key_saved_but_not_returned(self):
        destination=Path(self.temp.name)/'secret.json'
        value=save_config({'api_key':'test-key-not-real','model':'deepseek-flash'},destination)
        self.assertNotIn('api_key',value)
        self.assertEqual(json.loads(destination.read_text())['api_key'],'test-key-not-real')

if __name__=='__main__':unittest.main()
