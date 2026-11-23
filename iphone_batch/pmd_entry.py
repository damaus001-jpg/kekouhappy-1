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
    from pairing_patch import install as install_pairing, prevent_automatic_pairing
    install_pairing()
    prevent_automatic_pairing()
    from tunnel_target import install as install_targeted_tunnel
    install_targeted_tunnel()
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'trace-touch':
        import argparse
        import asyncio
        from touch_diagnostics import collect_phone, enabled
        parser = argparse.ArgumentParser()
        parser.add_argument('--udid', required=True)
        args = parser.parse_args(sys.argv[2:])
        if not enabled():
            parser.error('Touch tracing is available only in a development checkout')
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(collect_phone(args.udid))
        return
    if 'reset-workspace-session' in sys.argv:
        from media_recovery import install_cli
        install_cli()
    if 'serve-web' in sys.argv:
        from viewer_patch import install
        install()
    runpy.run_module('pymobiledevice3', run_name='__main__')


if __name__ == '__main__':
    main()
