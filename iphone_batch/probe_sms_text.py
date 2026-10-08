"""Read UI text locally and create a private, escaped review page; no translation."""
import argparse
from collections import Counter
from datetime import datetime
import html
import json
from pathlib import Path
import subprocess

from controller import command_for, device_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--udid', required=True)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--label', choices=['multi-baseline', 'multi-older'])
    args = parser.parse_args()
    samples = []
    for index in range(args.samples):
        process = subprocess.run(
            command_for(args.udid, ['developer', 'accessibility', 'list-items']),
            env=device_environment(args.udid), capture_output=True,
            text=True, encoding='utf-8', timeout=25,
        )
        if process.returncode:
            raise RuntimeError('UI text read failed; exit code ' + str(process.returncode))
        items = json.loads(process.stdout)
        samples.append(items)
        texts = [item.get('caption') or '' for item in items]
        print(json.dumps({'sample': index + 1, 'elements': len(items),
                          'nonempty_texts': sum(bool(text) for text in texts),
                          'max_text_length': max(map(len, texts), default=0)}, ensure_ascii=False))

    root = Path(__file__).resolve().parent / '.device-data' / 'diagnostics'
    root.mkdir(parents=True, exist_ok=True)
    stem = 'sms-text-' + args.udid[-8:]
    if args.label:
        stem += '-' + args.label
    record = {'device': args.udid, 'created': datetime.now().isoformat(),
              'scope': 'UI element captions, not yet classified as SMS', 'samples': samples}
    (root / (stem + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    sections = []
    for index, items in enumerate(samples, 1):
        rows = ''.join('<li><pre>' + html.escape(item.get('caption') or '[空文字]') + '</pre></li>' for item in items)
        sections.append(f'<details open><summary>第 {index} 次读取：{len(items)} 个元素</summary><ol>{rows}</ol></details>')
    document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>短信原文提取核对</title><style>body{font:16px system-ui;max-width:960px;margin:32px auto;padding:0 20px}'
                'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f6;padding:12px}summary{cursor:pointer}</style>'
                '<h1>短信原文提取核对</h1><p>下面是手机界面直接返回的文字，没有使用 OCR，也没有调用翻译服务。'
                '目前包含按钮、时间等界面描述，并非已整理的短信记录。请核对正文是否完整、是否漏字或带有描述前后缀。'
                '列表顺序是辅助功能遍历顺序，尚未确认等同于短信时间顺序。</p>' + ''.join(sections) + '</html>')
    page = root / (stem + '.html')
    page.write_text(document, encoding='utf-8')
    captions = [Counter(item.get('caption') or '' for item in items) for items in samples]
    print(json.dumps({'same_text_multiset': all(sample == captions[0] for sample in captions),
                      'review_page': str(page), 'raw_text_logged': False, 'external_api_called': False}))


if __name__ == '__main__':
    main()
