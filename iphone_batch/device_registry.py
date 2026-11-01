"""Reconcile USB discovery while retaining online device identities and ports."""
import re
import threading

MAX_DEVICES = 20

class DeviceRegistry:
    def __init__(self, devices, base_port=8080, dashboard_port=8070):
        self.devices = devices
        self.known = {device['udid']: device for device in devices}
        self.lock = threading.RLock()
        self.base_port = base_port
        self.dashboard_port = dashboard_port
        for index, device in enumerate(devices, 1):
            device.setdefault('number', str(index).zfill(2))

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
                    number = len(self.known) + 1
                    self.known[udid] = {'udid': udid, 'name': f'iPhone {number}',
                                        'number': str(number).zfill(2), 'port': port}
                    ports.add(port)
                added.append(self.known[udid])
            self.devices[:] = [device for device in self.devices if device['udid'] in online] + added
            return added, removed
