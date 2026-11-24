import unittest
from unittest.mock import Mock, patch
from dashboard import CpuUsage, FocusManager, discover_for_dashboard


class DiscoveryTests(unittest.TestCase):
    def test_missing_apple_service_allows_empty_workbench_and_later_recovery(self):
        devices=[{'udid':'one'}]
        with patch('dashboard.controller.discover',side_effect=[ConnectionRefusedError(10061,'refused'),devices]):
            rows,error=discover_for_dashboard()
            self.assertEqual(rows,[])
            self.assertIn('27015',error)
            self.assertIn('Apple Mobile Device Service',error)
            self.assertEqual(discover_for_dashboard(),(devices,None))

    def test_bad_usb_payload_keeps_workbench_available(self):
        devices=[{'udid':'one'}]
        with patch('dashboard.controller.discover',side_effect=[ValueError('bad plist'),devices]):
            rows,error=discover_for_dashboard()
            self.assertEqual(rows,[])
            self.assertIn('27015',error)
            self.assertEqual(discover_for_dashboard(),(devices,None))


class CpuUsageTests(unittest.TestCase):
    def readings(self, values):
        cpu = CpuUsage(reader=lambda: __import__('psutil').cpu_percent(interval=None))
        observed = []
        stopping = Mock()
        stopping.is_set.side_effect = [False] * len(values) + [True]
        stopping.wait.side_effect = lambda seconds: observed.append(cpu.snapshot())
        with patch('psutil.cpu_percent', side_effect=values) as read, patch('dashboard.time.monotonic', return_value=10):
            cpu.run(stopping)
        self.assertTrue(all(call.kwargs == {'interval': None} for call in read.call_args_list))
        self.assertTrue(all(call.args == (3,) for call in stopping.wait.call_args_list))
        return observed

    def test_first_sample_is_unknown_and_zero_is_a_valid_reading(self):
        self.assertEqual(self.readings([25, 0, 87.4]), [None, 0, 87.4])

    def test_sampling_failure_clears_load_and_rewarms_before_recovery(self):
        self.assertEqual(self.readings([25, 91, OSError('unavailable'), 45, 62]),
                         [None, 91, None, None, 62])

    def test_stale_sample_is_not_reported_as_current_load(self):
        cpu = CpuUsage()
        self.assertIsNone(cpu.snapshot())
        cpu.sample = (80, 10)
        with patch('dashboard.time.monotonic', return_value=14):
            self.assertEqual(cpu.snapshot(), 80)
        with patch('dashboard.time.monotonic', return_value=16):
            self.assertIsNone(cpu.snapshot())

    def test_sampling_thread_closes_system_counter_when_stopped(self):
        reader = Mock(return_value=20)
        stopping = Mock()
        stopping.is_set.side_effect = [False, False, True]
        CpuUsage(reader).run(stopping)
        reader.close.assert_called_once()

class FocusTests(unittest.TestCase):
    def setUp(self):
        self.devices=[{'udid':'one','port':8080},{'udid':'two','port':8081}]
        self.calls=[]
        self.manager=FocusManager(self.devices,'test-token',lambda device,active:self.calls.append((device['udid'],active)))

    def test_disable_before_enable_and_same_selection_idempotent(self):
        self.manager.select('one');self.manager.select('two');self.manager.select('two')
        self.assertEqual(self.calls,[('one',True),('one',False),('two',True)])
        self.assertEqual(self.manager.active,'two')

    def test_failure_disabling_old_phone_never_enables_new_phone(self):
        self.manager.select('one')
        def fail(device,active):
            self.calls.append((device['udid'],active))
            raise OSError('offline')
        self.manager.transport=fail
        with self.assertRaises(OSError):self.manager.select('two')
        self.assertEqual(self.calls,[('one',True),('one',False)])
        self.assertEqual(self.manager.active,'one')

    def test_failed_enable_revoked_and_no_owner_claimed(self):
        self.manager.select('one')
        def send(device,active):
            self.calls.append((device['udid'],active))
            if device['udid']=='two' and active:raise TimeoutError('reply lost')
        self.manager.transport=send
        with self.assertRaises(TimeoutError):self.manager.select('two')
        self.assertEqual(self.calls[-3:],[('one',False),('two',True),('two',False)])
        self.assertIsNone(self.manager.active)

    def test_unready_phone_can_be_selected_without_enabling_control(self):
        self.manager.select('two', ready=False)
        self.assertEqual(self.manager.selected, 'two')
        self.assertIsNone(self.manager.active)
        self.assertEqual(self.calls, [])
        self.manager.select('two')
        self.assertEqual(self.manager.active, 'two')
        self.assertEqual(self.calls, [('two', True)])

    def test_setup_selection_revokes_previous_control(self):
        self.manager.select('one')
        self.manager.select('two', ready=False)
        self.assertEqual(self.calls, [('one', True), ('one', False)])
        self.assertEqual(self.manager.selected, 'two')
        self.assertIsNone(self.manager.active)

    def test_unknown_setup_target_does_not_change_selection(self):
        self.manager.select('one')
        with self.assertRaises(ValueError):self.manager.select('missing', ready=False)
        self.assertEqual(self.manager.selected, 'one')
        self.assertEqual(self.manager.active, 'one')

    def test_unknown_target_does_not_touch_devices(self):
        with self.assertRaises(ValueError):self.manager.select('missing')
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
