import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from sms_tasks import SmsTaskRunner, SmsTaskWait


class SmsTaskRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.devices = {"phone-a": {}, "phone-b": {}}
        self.stopping = threading.Event()
        self.deliveries = []
        self.runner = SmsTaskRunner(
            self.temp.name, lambda: self.devices,
            self.deliver, self.stopping, max_workers=2,
        )

    def deliver(self, device, job, item, path):
        self.deliveries.append((device, item["number"], item["text"]))
        SmsTaskRunner.write_unit_status(path, json.loads(path.read_text(encoding="utf-8")),
                                        "sent_verified", sent_at="2026-11-22T12:00:00+00:00")
        return "sent_verified"

    def body(self, **overrides):
        value = {
            "name": "Test campaign",
            "numbers": ["+15550000001", "+15550000002", "+15550000003"],
            "texts": ["First", "Second"],
            "devices": {"phone-a": {"min": 1, "max": 2}, "phone-b": {"min": 1, "max": 2}},
            "concurrency": 2,
            "startMode": "immediate",
        }
        value.update(overrides)
        return value

    def test_immediate_task_assigns_each_number_once_and_verifies_completion(self):
        task = self.runner.create(self.body())
        self.assertEqual(task["status"], "queued")
        self.runner._run_job(task["id"])
        result = self.runner.snapshot(task["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["counts"], {"sent_verified": 3})
        self.assertEqual(sorted(number for _, number, _ in self.deliveries), sorted(self.body()["numbers"]))
        self.assertEqual(len({number for _, number, _ in self.deliveries}), 3)
        self.assertEqual([row[2] for row in sorted(self.deliveries, key=lambda row: row[1])],
                         ["First", "Second", "First"])

    def test_scheduled_task_is_persisted_without_sending_early(self):
        from datetime import datetime, timedelta, timezone
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        task = self.runner.create(self.body(startMode="scheduled", startAt=future))
        self.assertEqual(task["status"], "scheduled")
        self.assertEqual(task["start_at"], future)
        self.assertEqual(self.deliveries, [])
        restored = SmsTaskRunner(self.temp.name, lambda: self.devices, self.deliver,
                                 self.stopping, max_workers=2)
        self.assertEqual(restored.snapshot(task["id"])["status"], "scheduled")

    def test_explicit_resume_reconciles_receipt_and_sends_only_remaining_numbers(self):
        task = self.runner.create(self.body())
        job = self.runner.jobs[task['id']]
        first = job['items'][0]
        path = self.runner._write_unit(task['id'], first)
        unit = json.loads(path.read_text(encoding='utf-8'))
        SmsTaskRunner.write_unit_status(path, unit, 'sent_verified', sent_at='2026-11-22T12:00:00+00:00')
        first['status'] = 'failed'
        job['status'] = 'failed'
        result = self.runner.resume_unsent(task['id'])
        self.assertEqual(result['counts'], {'sent_verified': 1, 'queued': 2})
        self.runner._run_job(task['id'])
        self.assertEqual(self.runner.snapshot(task['id'])['counts'], {'sent_verified': 3})
        self.assertEqual({r[1] for r in self.deliveries}, set(self.body()['numbers'][1:]))

    def test_explicit_resume_rejects_send_marker_even_when_unit_still_ready(self):
        task = self.runner.create(self.body())
        job = self.runner.jobs[task['id']]
        job.update(status='failed')
        first = job['items'][0]
        first['status'] = 'failed'
        path = self.runner._write_unit(task['id'], first)
        unit = json.loads(path.read_text(encoding='utf-8'))
        unit['send_requested_at'] = '2026-11-22T12:00:00+00:00'
        path.write_text(json.dumps(unit), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '禁止自动重发'):
            self.runner.resume_unsent(task['id'])
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(first['status'], 'failed')

    def test_explicit_resume_rejects_receipt_for_different_recipient(self):
        task = self.runner.create(self.body())
        job = self.runner.jobs[task['id']]
        job['status'] = 'failed'
        path = self.runner._write_unit(task['id'], job['items'][0])
        unit = json.loads(path.read_text(encoding='utf-8'))
        unit.update(number='+15559999999', status='sent_verified')
        path.write_text(json.dumps(unit), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '不匹配'):
            self.runner.resume_unsent(task['id'])

    def test_scheduled_task_runs_once_when_due(self):
        from datetime import datetime, timedelta, timezone
        import time
        future = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        task = self.runner.create(self.body(
            numbers=["+15550000001"], texts=["Scheduled"],
            devices={"phone-a": {"min": 1, "max": 1}}, concurrency=1,
            startMode="scheduled", startAt=future))
        worker = threading.Thread(target=self.runner.run, daemon=True)
        worker.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.runner.snapshot(task["id"])["status"] == "completed":
                break
            time.sleep(.05)
        self.stopping.set()
        worker.join(timeout=2)
        result = self.runner.snapshot(task["id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["counts"], {"sent_verified": 1})
        self.assertEqual(self.deliveries, [("phone-a", "+15550000001", "Scheduled")])

    def test_duplicate_number_and_unzoned_schedule_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "重复"):
            self.runner.create(self.body(numbers=["+15550000001", "+15550000001"]))
        with self.assertRaisesRegex(ValueError, "时区"):
            self.runner.create(self.body(startMode="scheduled", startAt="2027-01-01T10:00:00"))

    def test_pre_send_temporary_device_loss_keeps_unit_queued(self):
        def wait_for_device(*_args):
            raise SmsTaskWait("device unavailable")
        self.runner.deliver = wait_for_device
        task = self.runner.create(self.body(numbers=["+15550000001"]))
        self.runner._run_job(task["id"])
        result = self.runner.snapshot(task["id"])
        self.assertEqual(result["status"], "waiting_for_device")
        self.assertEqual(result["counts"], {"queued": 1})

    def test_send_requested_failure_is_skipped_and_never_retried_after_restart(self):
        def uncertain(*_args):
            raise RuntimeError("connection lost after tap")
        self.runner.deliver = uncertain
        task = self.runner.create(self.body(numbers=["+15550000001"]))
        item = self.runner.snapshot(task["id"])["items"][0]
        path = self.runner.unit_path(task["id"], item["index"])

        def mark_then_fail(device, job, item, unit_path):
            SmsTaskRunner.write_unit_status(unit_path, json.loads(unit_path.read_text(encoding="utf-8")),
                                            "send_requested")
            raise RuntimeError("connection lost after tap")
        self.runner.deliver = mark_then_fail
        self.runner._run_job(task["id"])
        self.assertEqual(self.runner.snapshot(task["id"])["status"], "completed_with_errors")
        self.assertEqual(self.runner.snapshot(task["id"])["counts"], {"skipped": 1})
        restored = SmsTaskRunner(self.temp.name, lambda: self.devices, uncertain,
                                 self.stopping, max_workers=2)
        self.assertEqual(restored.snapshot(task["id"])["status"], "completed_with_errors")
        self.assertEqual(restored.snapshot(task["id"])["counts"], {"skipped": 1})
        self.assertEqual(self.deliveries, [])

    def test_restart_reclassifies_running_send_requested_unit_as_uncertain(self):
        task = self.runner.create(self.body(numbers=["+15550000001"]))
        job = self.runner.jobs[task["id"]]
        job["status"] = "running"
        job["items"][0].update(status="sending")
        path = self.runner._write_unit(task["id"], job["items"][0])
        unit = json.loads(path.read_text(encoding="utf-8"))
        SmsTaskRunner.write_unit_status(path, unit, "send_requested")
        self.runner._save(job)
        restored = SmsTaskRunner(self.temp.name, lambda: self.devices, self.deliver,
                                 self.stopping, max_workers=2)
        self.assertEqual(restored.snapshot(task["id"])["status"], "uncertain")
        self.assertEqual(restored.snapshot(task["id"])["counts"], {"uncertain": 1})

    def test_uncertain_number_does_not_stop_later_numbers(self):
        task = self.runner.create(self.body())
        first_number = self.body()["numbers"][0]

        def fail_first_then_send(device, job, item, unit_path):
            if item["number"] == first_number and item.get("attempts") == 1:
                SmsTaskRunner.write_unit_status(
                    unit_path, json.loads(unit_path.read_text(encoding="utf-8")),
                    "send_requested")
                raise RuntimeError("connection lost after tap")
            return self.deliver(device, job, item, unit_path)
        self.runner.deliver = fail_first_then_send
        self.runner._run_job(task["id"])
        final = self.runner.snapshot(task["id"])
        self.assertEqual(final["status"], "completed_with_errors")
        self.assertEqual(final["counts"], {"sent_verified": 2, "skipped": 1})
        self.assertEqual({r[1] for r in self.deliveries}, set(self.body()["numbers"][1:]))

    def test_failed_number_does_not_stop_later_numbers(self):
        task = self.runner.create(self.body())
        first_number = self.body()["numbers"][0]

        def fail_first(device, job, item, unit_path):
            if item["number"] == first_number and item.get("attempts") == 1:
                raise RuntimeError("network error before send")
            return self.deliver(device, job, item, unit_path)
        self.runner.deliver = fail_first
        self.runner._run_job(task["id"])
        final = self.runner.snapshot(task["id"])
        self.assertEqual(final["status"], "completed_with_errors")
        self.assertEqual(final["counts"], {"sent_verified": 2, "failed": 1})
        self.assertEqual({r[1] for r in self.deliveries}, set(self.body()["numbers"][1:]))

    def test_resume_completed_with_errors_requeues_failed_and_keeps_skipped(self):
        task = self.runner.create(self.body())
        job = self.runner.jobs[task["id"]]
        first, second = job["items"][0], job["items"][1]
        path = self.runner._write_unit(task["id"], first)
        first.update(status="failed", error="network error")
        path2 = self.runner._write_unit(task["id"], second)
        unit2 = json.loads(path2.read_text(encoding="utf-8"))
        unit2["send_requested_at"] = "2026-11-22T12:00:00+00:00"
        SmsTaskRunner.write_unit_status(path2, unit2, "send_requested")
        second.update(status="skipped", error="发送结果不明，已跳过且未重发；请核对手机")
        job["status"] = "completed_with_errors"
        self.runner._save(job)
        result = self.runner.resume_unsent(task["id"])
        self.assertEqual(result["counts"], {"skipped": 1, "queued": 2})
        self.runner._run_job(task["id"])
        final = self.runner.snapshot(task["id"])
        self.assertEqual(final["status"], "completed_with_errors")
        self.assertEqual(final["counts"], {"sent_verified": 2, "skipped": 1})
        self.assertEqual({r[1] for r in self.deliveries}, {first["number"], self.body()["numbers"][2]})

    def test_resume_include_uncertain_requeues_skipped_number_after_owner_check(self):
        task = self.runner.create(self.body())
        job = self.runner.jobs[task["id"]]
        first = job["items"][0]
        path = self.runner._write_unit(task["id"], first)
        unit = json.loads(path.read_text(encoding="utf-8"))
        unit["send_requested_at"] = "2026-11-22T12:00:00+00:00"
        SmsTaskRunner.write_unit_status(path, unit, "send_requested")
        first.update(status="skipped", error="发送结果不明，已跳过且未重发；请核对手机")
        job["status"] = "completed_with_errors"
        self.runner._save(job)
        result = self.runner.resume_unsent(task["id"], include_uncertain=True)
        self.assertEqual(result["counts"], {"queued": 3})
        requeued_unit = self.runner._read_unit(self.runner._unit_path(task["id"], first["index"]))
        self.assertEqual(requeued_unit["status"], "ready")
        self.assertNotIn("send_requested_at", requeued_unit)

    def test_resume_uncertain_skips_unknown_number_and_sends_remaining(self):
        task = self.runner.create(self.body())
        job = self.runner.jobs[task['id']]
        first = job['items'][0]
        path = self.runner._write_unit(task['id'], first)
        unit = json.loads(path.read_text(encoding='utf-8'))
        unit['send_requested_at'] = '2026-11-22T12:00:00+00:00'
        SmsTaskRunner.write_unit_status(path, unit, 'send_requested')
        first['status'] = 'uncertain'
        first['error'] = '发送结果不明，请核对手机；禁止自动重发'
        job['status'] = 'uncertain'
        self.runner._save(job)
        result = self.runner.resume_unsent(task['id'])
        self.assertEqual(result['counts'], {'skipped': 1, 'queued': 2})
        skipped = next(i for i in result['items'] if i['status'] == 'skipped')
        self.assertEqual(skipped['number'], self.body()['numbers'][0])
        self.runner._run_job(task['id'])
        final = self.runner.snapshot(task['id'])
        self.assertEqual(final['status'], 'completed_with_errors')
        self.assertEqual(final['counts'], {'sent_verified': 2, 'skipped': 1})
        self.assertEqual({r[1] for r in self.deliveries}, set(self.body()['numbers'][1:]))
        # The durable send marker for the skipped number is untouched.
        skipped_unit = self.runner._read_unit(self.runner._unit_path(task['id'], skipped['index']))
        self.assertEqual(skipped_unit['status'], 'send_requested')
        self.assertEqual(skipped_unit['send_requested_at'], '2026-11-22T12:00:00+00:00')

    def test_resume_rejects_tasks_that_are_not_failed_or_uncertain(self):
        task = self.runner.create(self.body())
        with self.assertRaisesRegex(ValueError, '失败、待核对或部分完成'):
            self.runner.resume_unsent(task['id'])

    def test_create_removes_numbers_already_sent_today_by_earlier_task(self):
        first = self.runner.create(self.body())
        self.runner._run_job(first["id"])
        second = self.runner.create(self.body(numbers=["+15550000001", "+15559999999"]))
        self.assertEqual(second["total"], 1)
        self.assertEqual(second["removed_duplicates"], ["+15550000001"])
        self.assertEqual(second["counts"], {"queued": 1})

    def test_create_rejects_list_fully_sent_today(self):
        first = self.runner.create(self.body())
        self.runner._run_job(first["id"])
        with self.assertRaisesRegex(ValueError, "今天都已发送过"):
            self.runner.create(self.body())

    def test_create_keeps_numbers_sent_on_earlier_days(self):
        from datetime import timedelta
        first = self.runner.create(self.body())
        self.runner._run_job(first["id"])
        job = self.runner.jobs[first["id"]]
        job["created_at"] = (datetime.now(timezone.utc).astimezone() - timedelta(days=1)).isoformat()
        self.runner._save(job)
        second = self.runner.create(self.body())
        self.assertEqual(second["total"], 3)
        self.assertEqual(second["removed_duplicates"], [])

    def test_navigation_failure_stops_only_that_device(self):
        numbers = ["+15550000001", "+15550000002", "+15550000003"]
        task = self.runner.create(self.body(numbers=numbers))

        def return_fail(device, job, item, path):
            self.deliver(device, job, item, path)
            if device == "phone-a":
                raise RuntimeError("return navigation failed")
            return "sent_verified"
        self.runner.deliver = return_fail
        self.runner._run_job(task["id"])
        final = self.runner.snapshot(task["id"])
        self.assertEqual(final["status"], "failed")
        self.assertIn("该设备已停止", final["error"])
        self.assertEqual(final["counts"], {"sent_verified": 2, "queued": 1})
        self.assertEqual({r[1] for r in self.deliveries}, {numbers[0], numbers[1]})

    def test_gap_starts_at_send_action_and_receipt_time_is_included(self):
        clock = [1000.0]
        calls, waits = [], []
        def deliver(device, job, item, path):
            calls.append(clock[0])
            unit = json.loads(path.read_text())
            unit['send_requested_at'] = datetime.fromtimestamp(clock[0], timezone.utc).isoformat()
            clock[0] += 20  # receipt verification and navigation back to list
            SmsTaskRunner.write_unit_status(path, unit, 'sent_verified',
                sent_at=datetime.fromtimestamp(clock[0], timezone.utc).isoformat())
            return 'sent_verified'
        def wait(seconds):
            waits.append(seconds)
            snapshot = self.runner.snapshot(task['id'])
            self.assertEqual(snapshot['waiting_next_compose'], 1)
            self.assertEqual(snapshot['in_flight'], 0)
            clock[0] += seconds
            return True
        self.runner.deliver = deliver
        task = self.runner.create(self.body(numbers=['+15550000001', '+15550000002'],
            devices={'phone-a': {'min': 30, 'max': 30}}, concurrency=1))
        with patch('sms_tasks.time.time', side_effect=lambda: clock[0]), \
                patch.object(self.runner, '_wait_interval', side_effect=wait):
            self.runner._run_job(task['id'])
        self.assertEqual(calls, [1000, 1030])
        self.assertEqual(waits, [10])

    def test_slow_receipt_does_not_add_another_full_interval(self):
        clock = [1000.0]
        def deliver(device, job, item, path):
            unit = json.loads(path.read_text())
            unit['send_requested_at'] = datetime.fromtimestamp(clock[0], timezone.utc).isoformat()
            clock[0] += 40
            SmsTaskRunner.write_unit_status(path, unit, 'sent_verified',
                sent_at=datetime.fromtimestamp(clock[0], timezone.utc).isoformat())
            return 'sent_verified'
        self.runner.deliver = deliver
        task = self.runner.create(self.body(numbers=['+15550000001', '+15550000002'],
            devices={'phone-a': {'min': 30, 'max': 30}}, concurrency=1))
        with patch('sms_tasks.time.time', side_effect=lambda: clock[0]), \
                patch.object(self.runner, '_wait_interval') as wait:
            self.runner._run_job(task['id'])
        wait.assert_not_called()

    def test_waiting_next_compose_does_not_reserve_slot_for_other_devices(self):
        entered_wait = threading.Event()
        other_sent = threading.Event()
        def deliver(device, job, item, path):
            self.deliver(device, job, item, path)
            if device == 'phone-b':
                other_sent.set()
            return 'sent_verified'
        def wait(_seconds):
            entered_wait.set()
            self.assertTrue(other_sent.wait(2), 'second device was starved by the first device interval')
            return True
        self.runner.deliver = deliver
        task = self.runner.create(self.body(concurrency=1))
        # Use current action timestamps so device A genuinely has an interval to wait.
        def delivery(device, job, item, path):
            result = deliver(device, job, item, path)
            unit = json.loads(path.read_text())
            unit['send_requested_at'] = datetime.now(timezone.utc).isoformat()
            path.write_text(json.dumps(unit))
            return result
        self.runner.deliver = delivery
        with patch.object(self.runner, '_wait_interval', side_effect=wait):
            self.runner._run_job(task['id'])
        self.assertTrue(entered_wait.is_set())
        self.assertEqual(self.runner.snapshot(task['id'])['status'], 'completed')

    def test_api_and_legacy_tasks_never_exceed_three_in_flight(self):
        self.devices.update({'phone-c': {}, 'phone-d': {}})
        devices = {device: {'min': 1, 'max': 1} for device in self.devices}
        with self.assertRaisesRegex(ValueError, '3'):
            self.runner.create(self.body(devices=devices, concurrency=4))
        task = self.runner.create(self.body(devices=devices, concurrency=3,
            numbers=['+15550000001', '+15550000002', '+15550000003', '+15550000004']))
        self.runner.jobs[task['id']]['concurrency'] = 20  # legacy persisted configuration
        self.runner._save(self.runner.jobs[task['id']])
        runner = SmsTaskRunner(self.temp.name, lambda: self.devices, self.deliver, self.stopping, max_workers=20)
        self.assertEqual(runner.max_workers, 3)
        active = [0, 0]
        lock = threading.Lock()
        barrier = threading.Barrier(3)
        def deliver(device, job, item, path):
            with lock:
                active[0] += 1
                active[1] = max(active)
            try:
                if item['index'] < 3:
                    barrier.wait(timeout=3)
                return self.deliver(device, job, item, path) or 'sent_verified'
            finally:
                with lock:
                    active[0] -= 1
        runner.deliver = deliver
        runner._run_job(task['id'])
        self.assertEqual(active[1], 3)
        self.assertEqual(runner.snapshot(task['id'])['status'], 'completed')

    def test_known_send_then_return_failure_stops_without_reclassifying_or_replaying_send(self):
        def deliver(device, job, item, path):
            self.deliver(device, job, item, path)
            raise RuntimeError('return navigation failed')
        self.runner.deliver = deliver
        task = self.runner.create(self.body(numbers=['+15550000001']))
        self.runner._run_job(task['id'])
        result = self.runner.snapshot(task['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['counts'], {'sent_verified': 1})
        self.assertIn('返回短信列表失败', result['error'])
        restored = SmsTaskRunner(self.temp.name, lambda: self.devices, self.deliver, self.stopping)
        self.assertEqual(restored.snapshot(task['id'])['status'], 'failed')
        self.assertEqual(len(self.deliveries), 1)

    def test_restart_keeps_send_action_interval_for_next_unsent_number(self):
        task = self.runner.create(self.body(numbers=['+15550000001', '+15550000002'],
            devices={'phone-a': {'min': 30, 'max': 30}}, concurrency=1))
        job = self.runner.jobs[task['id']]
        job['status'] = 'running'
        job['items'][0].update(status='sending', next_delay_seconds=30)
        path = self.runner._write_unit(task['id'], job['items'][0])
        unit = json.loads(path.read_text())
        unit['send_requested_at'] = datetime.fromtimestamp(1000, timezone.utc).isoformat()
        SmsTaskRunner.write_unit_status(path, unit, 'sent_verified',
            sent_at=datetime.fromtimestamp(1020, timezone.utc).isoformat())
        self.runner._save(job)
        restored = SmsTaskRunner(self.temp.name, lambda: self.devices, self.deliver, self.stopping)
        waits = []
        with patch('sms_tasks.time.time', return_value=1020), \
                patch.object(restored, '_wait_interval', side_effect=lambda delay: waits.append(delay) or True):
            restored._run_job(task['id'])
        self.assertEqual(waits, [10])
        self.assertEqual(len(self.deliveries), 1)


if __name__ == "__main__":
    unittest.main()
