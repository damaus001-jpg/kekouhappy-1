import threading
import unittest
from contextlib import nullcontext
from device_registry import DeviceRegistry
from notification_monitor import NotificationMonitor


class DeviceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.one={'udid':'one','name':'iPhone 1','port':8080}
        self.two={'udid':'two','name':'iPhone 2','port':8081}
        self.devices=[self.one,self.two]
        self.registry=DeviceRegistry(self.devices)

    def test_rescan_keeps_online_device_objects_order_and_ports(self):
        added,removed=self.registry.refresh([{'udid':'two'},{'udid':'one'}])
        self.assertEqual((added,removed),([],[]))
        self.assertIs(self.devices[0],self.one)
        self.assertEqual([d['port'] for d in self.devices],[8080,8081])

    def test_add_remove_and_reconnect_preserve_identity(self):
        added,removed=self.registry.refresh([{'udid':'two'},{'udid':'three'}])
        self.assertEqual(removed,[self.one])
        self.assertEqual(added[0]['port'],8082)
        self.assertEqual([d['number'] for d in self.devices],['02','03'])
        added,removed=self.registry.refresh([{'udid':'one'},{'udid':'two'},{'udid':'three'}])
        self.assertIs(added[0],self.one)
        self.assertEqual(added[0]['port'],8080)

    def test_empty_scan_removes_every_offline_device(self):
        added,removed=self.registry.refresh([])
        self.assertEqual(self.devices,[])
        self.assertEqual(removed,[self.one,self.two])

    def test_invalid_scan_does_not_change_current_devices(self):
        for rows in [[{'udid':'../bad'}],[{'udid':str(n)} for n in range(21)]]:
            with self.assertRaises(ValueError):self.registry.refresh(rows)
            self.assertEqual(self.devices,[self.one,self.two])

    def test_refresh_from_three_to_sixteen_keeps_existing_devices(self):
        self.registry.refresh([{'udid':name} for name in ['one','two','three']])
        previous=list(self.devices)
        rows=[{'udid':name} for name in ['one','two','three',*[f'phone-{n}' for n in range(13)]]]
        added,removed=self.registry.refresh(rows)
        self.assertEqual(len(self.devices),16)
        self.assertEqual(len(added),13)
        self.assertEqual(removed,[])
        self.assertTrue(all(before is after for before,after in zip(previous,self.devices)))
        self.assertEqual(len({d['port'] for d in self.devices}),16)
        self.assertEqual(len({d['number'] for d in self.devices}),16)
        self.assertNotIn(8070,{d['port'] for d in self.devices})
        self.assertEqual(self.registry.refresh(rows),([],[]))

    def test_twenty_devices_are_allowed_but_twenty_one_rejected_atomically(self):
        rows=[{'udid':str(n)} for n in range(20)]
        self.registry.refresh(rows)
        self.assertEqual(len(self.devices),20)
        before=list(self.devices)
        with self.assertRaisesRegex(ValueError,'20'):
            self.registry.refresh(rows+[{'udid':'extra'}])
        self.assertEqual(self.devices,before)

    def test_monitor_registers_new_devices_and_keeps_existing_state(self):
        monitor=NotificationMonitor(self.devices,threading.RLock(),lambda device:nullcontext(),
            lambda *args:{'items':[]},lambda device:False,threading.Event())
        monitor.protect('one',True)
        self.registry.refresh([{'udid':'one'},{'udid':'three'}])
        monitor.update_devices(self.devices)
        self.assertTrue(monitor.snapshot('one')['protected'])
        self.assertEqual(monitor.snapshot('three')['state'],'waiting')
        self.assertEqual([d['udid'] for d in monitor.devices],['one','three'])
