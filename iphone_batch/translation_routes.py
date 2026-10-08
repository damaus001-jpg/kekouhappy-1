"""Dispatch local translation requests, shared by dashboard and single-device viewer."""
import json
import os
import urllib.request
from translation import save_config, TranslationError
from text_translation import TextTranslationService

_service=None

def dispatch(service,device,body):
    action=body.get('action') if isinstance(body,dict) else None
    if action=='status':return service.status()
    if action=='config':return save_config(body)
    if action=='text':return service.translate_texts(device,body.get('contact'),body.get('texts'))
    if action=='frame':return service.frame(device,body)
    if action=='clear':
        scope=body.get('scope')
        if scope=='all':return service.cache.clear()
        if scope=='device':return service.cache.clear(device)
        if scope=='contact' and isinstance(body.get('contact'),str) and body['contact'].strip():
            return service.cache.clear(device,body['contact'].strip())
        raise ValueError('Invalid cache scope')
    raise ValueError('Invalid translation action')


def request(device,body):
    global _service
    address=os.environ.get('IPHONE_BATCH_TRANSLATION_URL')
    if address:
        payload={**body,'device':device}
        req=urllib.request.Request(address,data=json.dumps(payload).encode(),headers={
            'Content-Type':'application/json','X-Control-Token':os.environ.get('IPHONE_BATCH_CONTROL_TOKEN','')},method='POST')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req,timeout=50) as response:result=json.load(response)
        except Exception:
            raise TranslationError('翻译服务暂时不可用，请检查管理页面') from None
        if 'error' in result:raise TranslationError(result['error'])
        return result
    if _service is None:_service=TextTranslationService()
    return dispatch(_service,device,body)
