"""Passive trust investigation: Windows events, USB enumeration and local files.

Does not pair, start phone services, read messages, request backups or prevent
sleep. Device trust popups themselves must be marked by the human observer.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.request

import controller

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / '.device-data' / 'diagnostics' / 'trust-watch'


class Journal:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def emit(self, event, **data):
        now = datetime.now(timezone.utc)
        line = json.dumps({'utc': now.isoformat(), 'local': now.astimezone().isoformat(),
            'monotonic': round(time.monotonic(), 3), 'event': event, **data}, ensure_ascii=False)
        with self.lock, self.path.open('a', encoding='utf8') as output:
            output.write(line + '\n')


def windows_events(journal, stopped, ready):
    import win32api
    import win32gui
    import win32ts
    hwnd = None
    registered = False
    try:
        session_events = {7: 'session_locked', 8: 'session_unlocked',
            1: 'console_connected', 2: 'console_disconnected', 5: 'session_logon', 6: 'session_logoff'}
        power_events = {4: 'system_suspend', 7: 'system_resume', 18: 'system_resume_automatic', 10: 'power_status_changed'}

        def procedure(window, message, parameter, detail):
            if message == 0x02B1:
                journal.emit(session_events.get(parameter, 'session_change'), reason=parameter, session=detail)
            elif message == 0x0218:
                journal.emit(power_events.get(parameter, 'power_event'), reason=parameter)
                return 1
            elif message == 0x0219:
                journal.emit('device_change_notification', reason=parameter)
            return win32gui.DefWindowProc(window, message, parameter, detail)

        cls = win32gui.WNDCLASS()
        cls.hInstance = win32api.GetModuleHandle(None)
        cls.lpszClassName = 'IPhoneTrustWatch_' + str(os.getpid())
        cls.lpfnWndProc = procedure
        win32gui.RegisterClass(cls)
        hwnd = win32gui.CreateWindowEx(0, cls.lpszClassName, '', 0, 0, 0, 0, 0, 0, 0, cls.hInstance, None)
        win32ts.WTSRegisterSessionNotification(hwnd, 1)
        registered = True
        journal.emit('windows_notifications_ready')
        ready.set()
        while not stopped.wait(.25):
            win32gui.PumpWaitingMessages()
    except Exception as error:
        journal.emit('windows_notifications_error', error=type(error).__name__)
        ready.set()
    finally:
        if hwnd is not None:
            if registered:
                win32ts.WTSUnRegisterSessionNotification(hwnd)
            win32gui.DestroyWindow(hwnd)


def snapshot_state(opener):
    with opener.open('http://127.0.0.1:8070/api/state', timeout=6) as response:
        return json.load(response)


def run(seconds):
    FOLDER.mkdir(parents=True, exist_ok=True)
    current_path = FOLDER / 'current.json'
    if current_path.exists():
        prior = json.loads(current_path.read_text(encoding='utf8'))
        import psutil
        if psutil.pid_exists(prior['pid']):
            process = psutil.Process(prior['pid'])
            if str(Path(__file__).resolve()) in process.cmdline():
                raise RuntimeError('A trust observer is already running')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log = FOLDER / ('events-' + stamp + '.jsonl')
    stop_path = FOLDER / ('stop-' + stamp)
    journal = Journal(log)
    metadata = {'pid': os.getpid(), 'log': str(log), 'stop': str(stop_path), 'seconds': seconds,
                'started': datetime.now(timezone.utc).isoformat(), 'passive': True}
    current_path.write_text(json.dumps(metadata), encoding='utf8')
    journal.emit('started', **metadata)
    print(json.dumps(metadata), flush=True)
    stopped = threading.Event()
    notification_ready = threading.Event()
    thread = threading.Thread(target=windows_events, args=(journal, stopped, notification_ready), daemon=True)
    thread.start()
    notification_ready.wait(3)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    known = {}
    previous_usb = None
    previous_files = {}
    previous_viewers = None
    from pymobiledevice3.pair_records import OSUTILS
    record_folders = {'project': ROOT / '.device-data', 'apple': OSUTILS.pair_record_path}
    started = time.monotonic()
    last_sample = started
    next_sample = next_state = next_heartbeat = started
    try:
        while time.monotonic() - started < seconds and not stop_path.exists():
            now = time.monotonic()
            if now >= next_sample:
                if now - last_sample > 20:
                    journal.emit('sampling_gap', seconds=round(now - last_sample, 1))
                last_sample = now
                next_sample = now + 5
                try:
                    rows = controller.discover()  # ListDevices only; no lockdown/phone RPC.
                    usb = {row['udid']: row['device_id'] for row in rows}
                    if previous_usb is None:
                        journal.emit('usb_baseline', devices=[{'device': key, 'usb_id': value} for key, value in usb.items()])
                    else:
                        for device in previous_usb.keys() - usb.keys():
                            journal.emit('usb_disconnected', device=device, number=known.get(device))
                        for device, usb_id in usb.items():
                            if device not in previous_usb:
                                journal.emit('usb_connected', device=device, number=known.get(device), usb_id=usb_id)
                            elif previous_usb[device] != usb_id:
                                journal.emit('usb_reenumerated', device=device, number=known.get(device), usb_id=usb_id)
                    previous_usb = usb
                except Exception as error:
                    journal.emit('usb_enumeration_error', error=type(error).__name__)
                for source, folder in record_folders.items():
                    paths = {p.name: p for p in folder.glob('*.plist') if p.stem.startswith('0000')}
                    for name, path in paths.items():
                        key = (source, name)
                        try:
                            stat = path.stat()
                            signature = (stat.st_mtime_ns, stat.st_size)
                            old = previous_files.get(key)
                            if old is None or old[:2] != signature:
                                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                                journal.emit('pair_record_baseline' if old is None else 'pair_record_changed',
                                    source=source, device=path.stem, number=known.get(path.stem), modified_ns=stat.st_mtime_ns,
                                    size=stat.st_size, digest=digest)
                                previous_files[key] = (*signature, digest)
                        except (OSError, ValueError) as error:
                            journal.emit('pair_record_observation_error', source=source, device=path.stem, error=type(error).__name__)
                    for key in list(previous_files):
                        if key[0] == source and key[1] not in paths:
                            journal.emit('pair_record_removed', source=source, device=Path(key[1]).stem)
                            del previous_files[key]
            if now >= next_state:
                next_state = now + 15
                try:
                    state = snapshot_state(opener)
                    known.update((row['udid'], row['number']) for row in state['devices'])
                    viewers = {row['number']: {'ready': row['ready'], 'error': row.get('error')} for row in state['devices']}
                    if viewers != previous_viewers:
                        journal.emit('viewer_state', devices=viewers)
                        previous_viewers = viewers
                except Exception as error:
                    journal.emit('dashboard_query_error', error=type(error).__name__)
            if now >= next_heartbeat:
                next_heartbeat = now + 60
                journal.emit('heartbeat', usb_count=len(previous_usb or {}), elapsed=round(now - started, 1))
            stopped.wait(.5)
    finally:
        stopped.set()
        thread.join(timeout=3)
        journal.emit('stopped')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'status', 'stop', 'mark'))
    parser.add_argument('--seconds', type=int, default=86400)
    parser.add_argument('--device')
    parser.add_argument('--event', choices=('trust_prompt', 'trust_confirmed', 'hub_power_cycle', 'reading_started',
        'maintenance_started', 'maintenance_finished'))
    args = parser.parse_args()
    if args.action == 'run':
        if not 1 <= args.seconds <= 86400:
            parser.error('duration must be between 1 and 86400 seconds')
        return run(args.seconds)
    metadata = json.loads((FOLDER / 'current.json').read_text(encoding='utf8'))
    if args.action == 'stop':
        Path(metadata['stop']).touch()
    elif args.action == 'mark':
        if not args.event:
            parser.error('--event is required for mark')
        Journal(Path(metadata['log'])).emit('observer_mark', kind=args.event, number=args.device)
    else:
        import psutil
        metadata['running'] = psutil.pid_exists(metadata['pid'])
        print(json.dumps(metadata))


if __name__ == '__main__':
    main()
