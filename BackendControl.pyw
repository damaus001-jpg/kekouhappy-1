"""Double-click entry point; use this project's installed environment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'iphone_batch'))
from backend_control import main

if __name__ == '__main__':
    try:
        main(smoke_test='--smoke-test' in sys.argv)
    except Exception as error:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(error), '后台控制程序无法打开', 16)
        raise
