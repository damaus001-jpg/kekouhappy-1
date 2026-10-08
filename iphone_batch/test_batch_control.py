import asyncio
import json
from test_viewer_patch import ClipboardHTTPTests

class BatchControlHTTPTests(ClipboardHTTPTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.instance._batch_token='unit-test'
        self.instance._hid_queue=asyncio.Queue()
        self.instance._uhs=None
        self.instance._kb_service_id=None

    # Inherit the transport fixture, not standalone-viewer assertions.
    async def test_unicode_round_trip(self):
        code,_=await self.request('POST',{'text':'blocked'})
        self.assertEqual(code,403)
        code,_=await self.request()
        self.assertEqual(code,403)
        self.assertIsNone(self.clipboard)

    async def test_invalid_and_oversized_text_rejected(self):
        code,_=await self.request('POST',{'active':True},path='/control-mode',token='wrong')
        self.assertEqual(code,403)
        code,data=await self.request('POST',{'active':True},path='/control-mode',token='unit-test')
        self.assertEqual(code,200)
        self.assertTrue(json.loads(data)['active'])
        code,_=await self.request('POST',{'text':'allowed'})
        self.assertEqual(code,200)
        self.assertEqual(self.clipboard,'allowed')
        self.instance._hid_queue.put_nowait(('/key',b'{}'))
        code,_=await self.request('POST',{'active':False},path='/control-mode',token='unit-test')
        self.assertEqual(code,200)
        self.assertTrue(self.instance._hid_queue.empty())
        code,_=await self.request('POST',{'text':'blocked'})
        self.assertEqual(code,403)
        self.assertEqual(self.clipboard,'allowed')
        code,_=await self.instance._handle_key(b'{"usages":[4]}')
        self.assertEqual(code,403)
