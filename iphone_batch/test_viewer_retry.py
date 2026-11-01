import unittest
from viewer_retry import ViewerRetryPolicy


class ViewerRetryTests(unittest.TestCase):
    def test_disabled_developer_mode_never_restarts_without_refresh(self):
        policy=ViewerRetryPolicy()
        self.assertFalse(policy.should_retry('phone',1,'开发者模式未开启',100))
        for now in (103,160,1000,100000):
            self.assertFalse(policy.should_retry('phone',1,'开发者模式未开启',now))
        self.assertTrue(policy.requires_refresh('phone'))

    def test_missing_trust_and_disconnected_phone_wait_for_refresh(self):
        for error in ('无法建立手机可信连接，请解锁手机','Selected USB devices are not connected: phone'):
            policy=ViewerRetryPolicy()
            self.assertFalse(policy.should_retry('phone',1,error,100))
            self.assertTrue(policy.requires_refresh('phone'))

    def test_transient_retry_has_backoff_and_checks_do_not_postpone_it(self):
        policy=ViewerRetryPolicy()
        self.assertFalse(policy.should_retry('phone',1,'temporary disconnect',100))
        due=policy.states['phone']['due']
        self.assertGreaterEqual(due,130)
        self.assertFalse(policy.should_retry('phone',1,'temporary disconnect',due-1))
        self.assertEqual(policy.states['phone']['due'],due)
        self.assertTrue(policy.should_retry('phone',1,'temporary disconnect',due))
        self.assertFalse(policy.should_retry('phone',2,'temporary disconnect',due+1))
        self.assertGreaterEqual(policy.states['phone']['due'],due+61)

    def test_refresh_or_recovery_resets_previous_failure(self):
        policy=ViewerRetryPolicy()
        policy.should_retry('phone',1,'开发者模式未开启',100)
        policy.reset('phone')
        policy.should_retry('phone',2,'temporary disconnect',200)
        self.assertFalse(policy.requires_refresh('phone'))
        self.assertEqual(policy.states['phone']['failures'],1)

    def test_many_failures_are_staggered_and_backoff_is_bounded(self):
        policy=ViewerRetryPolicy()
        for n in range(16):policy.should_retry(f'phone-{n}',1,'temporary disconnect',100)
        self.assertGreater(len({state['due'] for state in policy.states.values()}),1)
        for generation in range(2,30):policy.should_retry('phone-0',generation,'temporary disconnect',1000)
        self.assertLessEqual(policy.states['phone-0']['due'],1312)
