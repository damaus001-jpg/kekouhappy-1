"""Capture cryptexd logs during one developer-image installation attempt."""
import asyncio
import argparse
import os
from pathlib import Path
import sys
import controller


async def diagnose(udid):
    folder = Path(__file__).resolve().parent / '.device-data' / 'diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    log_path = folder / 'cryptexd.log'
    flags = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    with log_path.open('wb') as output:
        watcher = await asyncio.create_subprocess_exec(
            *controller.command_for(udid, ['syslog', 'live', '--process-name', 'cryptexd']),
            env={**controller.device_environment(udid), 'PYTHONUNBUFFERED': '1'},
            stdout=output, stderr=output, **flags)
        try:
            await asyncio.sleep(3)
            if watcher.returncode is not None:
                raise RuntimeError('Log capture stopped; inspect ' + str(log_path))
            result = await controller.inspect_device(udid, 600, True)
            await asyncio.sleep(2)
        finally:
            if watcher.returncode is None:
                watcher.kill()
            await watcher.wait()
    print('\nDevice log: ' + str(log_path), flush=True)
    print('--- Last 60 cryptexd log lines ---', flush=True)
    print('\n'.join(log_path.read_text(encoding='utf-8', errors='replace').splitlines()[-60:]), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--udid')
    args = parser.parse_args()
    udid = controller.resolve_devices([args.udid] if args.udid else None)[0]
    with controller.device_lock(udid):
        return asyncio.run(diagnose(udid))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
