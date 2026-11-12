"""Run pymobiledevice3's shared tunnel daemon with project-local logs and cache."""
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / '.device-data' / 'logs' / 'tunneld.log'


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    sys.argv = [str(ROOT / 'pmd_entry.py'), 'remote', 'tunneld', '--no-wifi', '--no-mobdev2']
    with LOG.open('a', encoding='utf-8', buffering=1) as output:
        print('\n--- tunneld starting ---', file=output, flush=True)
        with redirect_stdout(output), redirect_stderr(output):
            from pmd_entry import main as pmd_main
            pmd_main()


if __name__ == '__main__':
    main()
