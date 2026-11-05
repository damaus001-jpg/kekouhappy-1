"""Reconcile USB discovery while retaining online device identities and ports."""
import re
import threading
import json
from pathlib import Path

MAX_DEVICES = 20

class DeviceRegistry:
    def __init__(self, devices, base_port=8080, dashboard_port=8070, state_path=None):
        online=[{'udid':device['udid']} for device in devices]
        self.state_path=Path(state_path) if state_path else None
        if self.state_path and self.state_path.exists():
            saved=json.loads(self.state_path.read_text(encoding='utf-8'))
            if not isinstance(saved,list):raise ValueError('设备编号存档无效')
            ids=set();ports=set();numbers=set()
            for row in saved:
                if (not isinstance(row,dict) or not isinstance(row.get('udid'),str)
                    or not re.fullmatch(r'[A-Za-z0-9-]+',row['udid'])
                    or not isinstance(row.get('number'),str) or not row['number'].isdigit()
                    or not isinstance(row.get('name'),str) or type(row.get('port')) is not int
                    or not 1024<=row['port']<=65535 or row['port']==dashboard_port
                    or row['udid'] in ids or row['port'] in ports or row['number'] in numbers):
                    raise ValueError('设备编号存档无效，已停止以避免重新编号')
                ids.add(row['udid']);ports.add(row['port']);numbers.add(row['number'])
            devices[:]=saved
        self.devices = devices
        self.known = {device['udid']: device for device in devices}
        self.lock = threading.RLock()
        self.base_port = base_port
        self.dashboard_port = dashboard_port
        for index, device in enumerate(devices, 1):
            device.setdefault('number', str(index).zfill(2))
        if self.state_path:
            self.refresh(online)
            self.save()

    def save(self):
        if not self.state_path:return
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        rows=[{key:device[key] for key in ('udid','name','number','port')} for device in self.known.values()]
        temporary=self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(self.state_path)

    def refresh(self, discovered):
        udids = list(dict.fromkeys(row['udid'] for row in discovered))
        if len(udids) > MAX_DEVICES:
            raise ValueError(f'当前工作台最多支持 {MAX_DEVICES} 台手机')
        if any(not isinstance(udid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', udid) for udid in udids):
            raise ValueError('USB 设备标识无效')
        with self.lock:
            online = set(udids)
            current = {device['udid'] for device in self.devices}
            removed = [device for device in self.devices if device['udid'] not in online]
            added = []
            ports = {device['port'] for device in self.known.values()} | {self.dashboard_port}
            for udid in udids:
                if udid in current:
                    continue
                if udid not in self.known:
                    port = self.base_port
                    while port in ports:
                        port += 1
                    if port > 65535:
                        raise ValueError('没有可用的投屏端口')
                    number = max((int(device['number']) for device in self.known.values()),default=0)+1
                    self.known[udid] = {'udid': udid, 'name': f'iPhone {number}',
                                        'number': str(number).zfill(2), 'port': port}
                    ports.add(port)
                added.append(self.known[udid])
            self.devices[:] = [device for device in self.devices if device['udid'] in online] + added
            if added or removed:self.save()
            return added, removed
