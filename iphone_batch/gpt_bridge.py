"""Copy conversation text and fill a ChatGPT web draft without submitting it."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from viewer_patch import windows_clipboard

_lock = threading.Lock()


def open_gpt_draft(text):
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 2*1024*1024:
        raise ValueError('汇总文字为空或超过 2MB，未打开 ChatGPT')
    if not _lock.acquire(blocking=False):
        raise ValueError('正在准备另一个 ChatGPT 草稿，请稍候')
    try:
        windows_clipboard(text, write=True)
        node = shutil.which('node')
        if not node:
            return {'status':'browser_unavailable', 'clipboard_copied':True}
        try:
            process = subprocess.run([node,str(Path(__file__).with_name('gpt_browser.cjs'))],
                input=json.dumps({'text':text},ensure_ascii=False),encoding='utf-8',
                capture_output=True,timeout=55,
                creationflags=0x08000000 if sys.platform=='win32' else 0)
            result=json.loads(process.stdout)
            if result.get('status') not in ('filled','existing_draft','unverified','page_not_ready','browser_error'):
                result={'status':'browser_error'}
        except (OSError, ValueError, subprocess.TimeoutExpired):
            result={'status':'browser_error'}
        return {**result,'clipboard_copied':True}
    finally:
        _lock.release()
