"""Run upstream CLI with its data cache contained in this workspace."""
from pathlib import Path
import runpy


def main():
    # Upstream 11.22 has no Windows data-directory CLI option. Override its
    # cached path in this child process only; never modify installed files or HOME.
    from pymobiledevice3 import common
    if not hasattr(common, '_HOMEFOLDER'):
        raise RuntimeError('Upstream cache API changed; update pmd_entry.py')
    common._HOMEFOLDER = Path(__file__).resolve().parent / '.device-data'
    import sys
    if 'serve-web' in sys.argv:
        from viewer_patch import install
        install()
    runpy.run_module('pymobiledevice3', run_name='__main__')


if __name__ == '__main__':
    main()
