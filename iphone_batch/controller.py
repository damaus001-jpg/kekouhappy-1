"""iPhone batch controller: process isolation per device, no shell commands."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import math
import os
import plistlib
import socket
import struct
import sys
import time
import hashlib
import tempfile
import contextlib
import urllib.request
from pathlib import Path

HID = ['developer', 'core-device', 'universal-hid-service']


def discover(host='127.0.0.1', port=27015):
    """Read usbmux enumeration only; never initiates pairing."""
    def receive(sock, length):
        data = bytearray()
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise RuntimeError('Apple service closed the connection')
            data.extend(chunk)
        return bytes(data)

    payload = plistlib.dumps({
        'MessageType': 'ListDevices', 'ClientVersionString': 'iphone-batch',
        'ProgName': 'iphone-batch', 'kLibUSBMuxVersion': 3,
    })
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(struct.pack('<IIII', 16 + len(payload), 1, 8, 1) + payload)
        length, version, message, tag = struct.unpack('<IIII', receive(sock, 16))
        if not 16 <= length <= 4 * 1024 * 1024 or version != 1 or message != 8 or tag != 1:
            raise RuntimeError('Invalid Apple service response')
        response = plistlib.loads(receive(sock, length - 16))
    if response.get('Number', 0):
        raise RuntimeError(f"Apple service error: {response['Number']}")
    devices = {}
    for entry in response.get('DeviceList', []):
        properties = entry.get('Properties', {})
        udid = properties.get('SerialNumber')
        if not udid or properties.get('ConnectionType') != 'USB':
            continue
        row = {'udid': udid, 'connection': properties.get('ConnectionType', 'Unknown'), 'device_id': entry['DeviceID']}
        if udid not in devices or row['connection'] == 'USB':
            devices[udid] = row
    return list(devices.values())



def read_device_info(udid):
    """Read pre-session lockdown values; never pairs, starts services or installs images."""
    rows = [row for row in discover() if row['udid'] == udid]
    if len(rows) != 1:
        raise ValueError('Selected USB device is not connected')

    def receive(sock, count):
        result = bytearray()
        while len(result) < count:
            data = sock.recv(count - len(result))
            if not data:
                raise RuntimeError('Device closed the connection')
            result.extend(data)
        return bytes(result)

    with socket.create_connection(('127.0.0.1', 27015), timeout=5) as sock:
        payload = plistlib.dumps({'MessageType': 'Connect',
                                 'DeviceID': rows[0]['device_id'],
                                 'PortNumber': socket.htons(62078),
                                 'ClientVersionString': 'iphone-batch',
                                 'ProgName': 'iphone-batch', 'kLibUSBMuxVersion': 3})
        sock.sendall(struct.pack('<IIII', len(payload) + 16, 1, 8, 1) + payload)
        length, version, message, tag = struct.unpack('<IIII', receive(sock, 16))
        if not 16 <= length <= 4 * 1024 * 1024 or version != 1 or message != 8 or tag != 1:
            raise RuntimeError('Invalid Apple service response')
        response = plistlib.loads(receive(sock, length - 16))
        if response.get('Number') != 0:
            raise RuntimeError(f"Apple connect error: {response.get('Number')}")
        request = plistlib.dumps({'Label': 'iphone-batch', 'Request': 'GetValue'})
        sock.sendall(struct.pack('>I', len(request)) + request)
        size = struct.unpack('>I', receive(sock, 4))[0]
        if not 0 < size <= 4 * 1024 * 1024:
            raise RuntimeError('Invalid lockdown response size')
        response = plistlib.loads(receive(sock, size))
        if response.get('Error'):
            raise RuntimeError('Lockdown rejected read-only query: ' + str(response['Error']))
        values = response.get('Value', {})
        if not isinstance(values, dict):
            raise RuntimeError('Invalid lockdown device values')
        fields = ('ProductType', 'ProductVersion', 'BuildVersion', 'DeviceClass',
                  'HardwareModel', 'CPUArchitecture')
        return {'udid': udid, **{key: values[key] for key in fields if key in values},
                'scope': 'Read-only device values; trust and developer services not verified'}


def coordinate(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535:
        raise ValueError('Coordinates must be integers between 0 and 65535')
    return value


def positive_duration(value, limit=300):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('Duration must be a number')
    if not math.isfinite(value) or not 0 < value <= limit:
        raise ValueError(f'Duration must be greater than 0 and at most {limit} seconds')
    return value


def compile_steps(steps):
    """Validate entire input before any device operation; never silently run unknown ops."""
    if not isinstance(steps, list) or not steps or len(steps) > 1000:
        raise ValueError('Script must contain 1 to 1000 steps')
    result = []
    gestures = []

    def flush():
        if gestures:
            result.append((HID + ['session'], '\n'.join(gestures) + '\n'))
            gestures.clear()

    for index, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            raise ValueError(f'Step {index} must be an object')
        op = step.get('op')
        if op == 'tap':
            x, y = coordinate(step.get('x')), coordinate(step.get('y'))
            gestures.append(f'tap {x} {y}')
        elif op == 'drag':
            points = [coordinate(step.get(key)) for key in ('x1', 'y1', 'x2', 'y2')]
            duration = positive_duration(step.get('duration', 0.6), 30)
            gestures.append('drag ' + ' '.join(map(str, points)) + f' 30 {duration}')
        elif op == 'sleep':
            gestures.append(f"sleep {positive_duration(step.get('seconds'))}")
        elif op == 'type':
            value = step.get('text')
            if not isinstance(value, str) or not value or len(value) > 2000:
                raise ValueError('Text must contain 1 to 2000 characters')
            if any(not (' ' <= char <= '~' or char in '\n\t') for char in value):
                raise ValueError('HID typing supports ASCII only; Chinese requires another input route')
            flush()
            result.append((HID + ['type', '--', value], None))
        else:
            raise ValueError(f'Step {index}: unsupported operation {op!r}; use tap, drag, sleep or type')
    flush()
    return result


def command_for(udid, args, python=sys.executable):
    # RSD-only commands do not declare --udid; all paths support the UDID environment.
    return [python, str(Path(__file__).resolve().with_name('pmd_entry.py')), *args]


def device_environment(udid):
    # A target cannot inherit another device, remote usbmux, or tunnel routing from its parent.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('PYMOBILEDEVICE3_') and key != 'USBMUXD_SOCKET_ADDRESS'}
    env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', NO_COLOR='1',
               PYMOBILEDEVICE3_UDID=udid,
               PYMOBILEDEVICE3_USBMUX='127.0.0.1:27015')
    return env


def emit(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)


async def run_device(udid, compiled, timeout):
    """One sequential pipeline per device; different device pipelines run concurrently."""
    for index, (args, script) in enumerate(compiled, 1):
        process = None
        try:
            env = device_environment(udid)
            flags = {'creationflags': 0x08000000} if os.name == 'nt' else {}
            process = await asyncio.create_subprocess_exec(
                *command_for(udid, args), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env, **flags,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(script.encode('utf-8') if script else None), timeout,
            )
            emit({'udid': udid, 'batch': index, 'status': 'command_completed' if process.returncode == 0 else 'failed',
                  'exit_code': process.returncode, 'stdout': stdout.decode('utf-8', 'replace')[-8000:],
                  'stderr': stderr.decode('utf-8', 'replace')[-8000:]})
            if process.returncode:
                return False
            if args == ['mounter', 'query-developer-mode-status']:
                mode = json.loads(stdout.decode('utf-8'))
                if mode is not True:
                    emit({'udid': udid, 'status': 'requires_developer_mode',
                          'message': 'Enable Developer Mode on the phone and complete its reboot confirmation'})
                    return False
        except asyncio.TimeoutError:
            emit({'udid': udid, 'batch': index, 'status': 'timeout',
                  'message': 'Operation may have partially executed; no automatic retry'})
            return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            emit({'udid': udid, 'batch': index, 'status': 'failed', 'message': str(exc)})
            return False
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.communicate()
    return True


async def run_all(udids, compiled, timeout, concurrency):
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(udid):
        async with semaphore:
            return await run_device(udid, compiled, timeout)

    results = await asyncio.gather(*(bounded(udid) for udid in udids))
    emit({'status': 'batch_finished', 'successful': sum(results), 'total': len(results),
          'note': 'Command exit status does not confirm the UI result'})
    return 0 if all(results) else 1




@contextlib.contextmanager
def device_lock(udid):
    """OS-owned advisory lock shared by all controller instances; released on crash."""
    digest = hashlib.sha256(udid.encode('utf-8')).hexdigest()
    folder = Path(tempfile.gettempdir()) / 'iphone-batch-locks'
    folder.mkdir(exist_ok=True)
    handle = (folder / (digest + '.lock')).open('a+b')
    locked = False
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise RuntimeError(f'Device {udid} is already owned by another controller') from exc
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def resolve_devices(requested):
    connected = {row['udid'] for row in discover()}
    if requested:
        udids = list(dict.fromkeys(requested))
    elif len(connected) == 1:
        udids = list(connected)
    else:
        raise ValueError('Connect exactly one USB device or explicitly select --udid')
    if len(udids) > 10:
        raise ValueError('This deployment is limited to 10 devices')
    if any(not udid.strip() or udid.startswith('-') for udid in udids):
        raise ValueError('Invalid UDID')
    missing = set(udids) - connected
    if missing:
        raise ValueError('Selected USB devices are not connected: ' + ', '.join(sorted(missing)))
    return udids


async def inspect_device(udid, timeout, prepare=False):
    emit({'status': 'device_info', **read_device_info(udid)})
    commands = [(['mounter', 'query-developer-mode-status'], None)]
    if prepare:
        commands.append((['mounter', 'auto-mount'], None))
    commands.append((['developer', 'core-device', 'display', 'get-media-support-info'], None))
    return 0 if await run_device(udid, commands, timeout) else 1


async def monitor_usb(udid, seconds, interval):
    started = time.monotonic()
    previous = None
    samples = 0
    missing_samples = 0
    probe_errors = 0
    disconnects = 0
    while time.monotonic() - started < seconds:
        try:
            present = udid in {row['udid'] for row in await asyncio.to_thread(discover)}
            samples += 1
            missing_samples += not present
            if previous is True and not present:
                disconnects += 1
            if present != previous:
                emit({'status': 'usb_connected' if present else 'usb_disconnected',
                      'udid': udid, 'elapsed_seconds': round(time.monotonic() - started, 2)})
            previous = present
        except (OSError, RuntimeError, ValueError) as exc:
            probe_errors += 1
            emit({'status': 'usb_probe_error', 'message': str(exc)})
        remaining = seconds - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(min(interval, remaining))
    passed = samples > 0 and missing_samples == 0 and probe_errors == 0
    emit({'status': 'usb_monitor_finished', 'udid': udid, 'passed': passed,
          'samples': samples, 'missing_samples': missing_samples,
          'probe_errors': probe_errors, 'observed_disconnects': disconnects,
          'elapsed_seconds': round(time.monotonic() - started, 2),
          'scope': 'USB presence only; video and touch stability are not measured'})
    return 0 if passed else 1


async def run_screen(udid, port):
    args = ['developer', 'core-device', 'display', 'serve-web',
            '--bind', '127.0.0.1', '--http-port', str(port), '--no-audio', '--no-motion-idr']
    flags = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    log_path = Path(__file__).resolve().parent / '.device-data' / 'diagnostics' / f'screen-{udid[-8:]}-{port}.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('wb') as output:
        process = await asyncio.create_subprocess_exec(
            *command_for(udid, args), env={**device_environment(udid), 'PYTHONUNBUFFERED': '1'},
            stdout=output, stderr=asyncio.subprocess.STDOUT, **flags)
    emit({'status': 'screen_starting', 'log': str(log_path)})
    url = f'http://127.0.0.1:{port}/'
    try:
        for _ in range(180):
            if process.returncode is not None:
                emit({'status': 'screen_failed', 'exit_code': process.returncode,
                      'log_tail': log_path.read_text(encoding='utf-8', errors='replace')[-6000:]})
                return process.returncode or 1
            try:
                def probe():
                    # Ignore proxy environment variables for this localhost-only viewer.
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(url, timeout=0.3) as response:
                        return response.status == 200
                if await asyncio.to_thread(probe):
                    emit({'status': 'viewer_http_ready', 'udid': udid, 'url': url})
                    return await process.wait()
            except OSError:
                pass
            await asyncio.sleep(0.25)
        emit({'status': 'error', 'message': 'Screen server did not become ready'})
        return 1
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def main():
    parser = argparse.ArgumentParser(description='iPhone 批量控制原型（Windows USB）')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('devices', help='发现手机，不触发配对')
    info = sub.add_parser('info', help='Read device model and OS without dependencies or pairing')
    info.add_argument('--udid')
    sub.add_parser('check', help='检查 Python 模块和设备发现')
    screen = sub.add_parser('screen', help='Serve one device screen in a local browser')
    screen.add_argument('--udid')
    screen.add_argument('--port', type=int, default=8080)
    run = sub.add_parser('run', help='向指定设备并行执行 JSON 脚本')
    run.add_argument('script', type=Path)
    run.add_argument('--udid', action='append', help='重复指定多个 UDID')
    run.add_argument('--dry-run', action='store_true', help='只预览，不连接手机')
    run.add_argument('--timeout', type=float, default=120, help='每组命令的超时秒数')
    run.add_argument('--concurrency', type=int, default=4)
    inspect = sub.add_parser('inspect', help='Check one USB device and media capabilities')
    inspect.add_argument('--udid')
    inspect.add_argument('--timeout', type=float, default=60)
    prepare = sub.add_parser('prepare', help='Install or mount the required developer image')
    prepare.add_argument('--udid')
    prepare.add_argument('--timeout', type=float, default=600)
    monitor = sub.add_parser('monitor', help='Measure USB presence without controlling the screen')
    monitor.add_argument('--udid')
    monitor.add_argument('--seconds', type=float, default=1800)
    monitor.add_argument('--interval', type=float, default=5)
    args = parser.parse_args()
    try:
        if args.action in ('devices', 'check'):
            rows = discover()
            data = {'devices': rows, 'count': len(rows)}
            if args.action == 'check':
                data.update(python=sys.executable, pymobiledevice3_installed=importlib.util.find_spec('pymobiledevice3') is not None)
            emit(data)
            return 0
        if args.action == 'info':
            udid = resolve_devices([args.udid] if args.udid else None)[0]
            emit(read_device_info(udid))
            return 0
        if args.action == 'monitor':
            positive_duration(args.seconds, 86400)
            positive_duration(args.interval, 60)
            udid = resolve_devices([args.udid] if args.udid else None)[0]
            return asyncio.run(monitor_usb(udid, args.seconds, args.interval))
        if args.action in ('inspect', 'prepare'):
            positive_duration(args.timeout, 86400)
            if importlib.util.find_spec('pymobiledevice3') is None:
                raise RuntimeError('Install pymobiledevice3 from your own terminal; this execution environment blocks PyPI')
            udid = resolve_devices([args.udid] if args.udid else None)[0]
            with device_lock(udid):
                return asyncio.run(inspect_device(udid, args.timeout, args.action == 'prepare'))
        if args.action == 'screen':
            if not 1024 <= args.port <= 65535:
                raise ValueError('Port must be between 1024 and 65535')
            if importlib.util.find_spec('pymobiledevice3') is None:
                raise RuntimeError('pymobiledevice3 is not installed; see README.md')
            udid = resolve_devices([args.udid] if args.udid else None)[0]
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', args.port))
            with device_lock(udid):
                return asyncio.run(run_screen(udid, args.port))
        compiled = compile_steps(json.loads(args.script.read_text(encoding='utf-8-sig')))
        positive_duration(args.timeout, 86400)
        if not 1 <= args.concurrency <= 64:
            raise ValueError('Concurrency must be between 1 and 64')
        udids = list(dict.fromkeys(args.udid or []))
        if any(not udid.strip() or udid.startswith('-') for udid in udids):
            raise ValueError('UDID must be nonempty and must not start with a hyphen')
        if args.dry_run:
            if not udids:
                raise ValueError('Dry run requires explicit --udid placeholders')
            if len(udids) > 10:
                raise ValueError('This deployment is limited to 10 devices')
            emit({'status': 'preview', 'devices': udids,
                  'commands': [{'udid': udid, 'argv': command_for(udid, command), 'target_env': {'PYMOBILEDEVICE3_UDID': udid, 'PYMOBILEDEVICE3_USBMUX': '127.0.0.1:27015'}, 'stdin': script}
                               for udid in udids for command, script in compiled]})
            return 0
        if importlib.util.find_spec('pymobiledevice3') is None:
            raise RuntimeError('pymobiledevice3 is not installed in this interpreter; see README.md')
        udids = resolve_devices(args.udid)
        with contextlib.ExitStack() as locks:
            for udid in sorted(udids):
                locks.enter_context(device_lock(udid))
            return asyncio.run(run_all(udids, compiled, args.timeout, args.concurrency))
    except (ValueError, OSError, RuntimeError) as exc:
        emit({'status': 'error', 'message': str(exc)})
        return 1
    except KeyboardInterrupt:
        emit({'status': 'cancelled', 'message': 'Running commands cancelled; completed actions remain'})
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
