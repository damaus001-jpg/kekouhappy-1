"""Translate extracted SMS text; never connect to or send to a phone."""
import argparse
import html
import json
from pathlib import Path
import time

from text_translation import TextTranslationService


def translate_file(source, service=None):
    source = Path(source)
    result = json.loads(source.read_text(encoding='utf-8-sig'))
    device, contact = result['device'], result['contact']
    if not device or not contact:
        raise ValueError('短信文件未确认设备或联系人，无法翻译')
    service = service or TextTranslationService()
    messages = result['messages']
    pending = [m for m in messages if m.get('kind', 'text') == 'text' and m.get('text', '').strip()]
    cache_hits = requests = 0
    for start in range(0, len(pending), 30):
        # The shared service limits new requests to one every four seconds.
        if start:
            time.sleep(max(0, 4.1 - (time.monotonic() - service.last_api_request)))
        batch = pending[start:start + 30]
        translated = service.translate_texts(device, contact, [m['text'] for m in batch])
        for message, text in zip(batch, translated['translations']):
            message['translation_zh'] = text
        cache_hits += translated['cache_hits']
        requests += translated['api_requests']
    result['translation'] = {'status': 'completed', 'model': service.status()['model'],
                             'messages': len(pending), 'cache_hits': cache_hits, 'api_requests': requests}
    destination = source.with_name(source.stem + '-translated.json')
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    rows = []
    for number, message in enumerate(pending, 1):
        side = '我方' if message.get('side') == 'outgoing' else '对方'
        rows.append('<article><b>' + str(number) + ' · ' + side + ' · ' + html.escape(message.get('time') or '')
                    + '</b><pre>' + html.escape(message['text']) + '</pre><pre class="zh">'
                    + html.escape(message['translation_zh']) + '</pre></article>')
    page = destination.with_suffix('.html')
    page.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                   '<meta name="viewport" content="width=device-width,initial-scale=1">'
                   '<title>短信中英对照</title><style>body{font:16px system-ui;max-width:900px;margin:30px auto;padding:0 20px}'
                   'pre{white-space:pre-wrap;overflow-wrap:anywhere}article{border-bottom:1px solid #ddd;padding:14px 0}'
                   '.zh{color:#14633e}</style><h1>短信中英对照</h1><p>联系人：' + html.escape(contact)
                   + '。译文由 DeepSeek 生成，图片已跳过。</p><p>范围为已提取记录，完整性与顺序以原始核对结果为准；重复记录保留。</p>'
                   + ''.join(rows) + '</html>', encoding='utf-8')
    return {**result['translation'], 'review_page': str(page), 'output': str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='已提取的短信 JSON 文件')
    args = parser.parse_args()
    print(json.dumps(translate_file(args.source), ensure_ascii=False))


if __name__ == '__main__':
    main()
