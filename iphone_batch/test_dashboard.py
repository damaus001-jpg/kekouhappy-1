import unittest
from dashboard import FocusManager

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

    def test_unknown_target_does_not_touch_devices(self):
        with self.assertRaises(ValueError):self.manager.select('missing')
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
