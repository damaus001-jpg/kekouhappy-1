import json
from pathlib import Path
import tempfile
import threading
import unittest

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

    def test_send_requested_failure_is_uncertain_and_never_retried_after_restart(self):
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
        self.assertEqual(self.runner.snapshot(task["id"])["status"], "uncertain")
        restored = SmsTaskRunner(self.temp.name, lambda: self.devices, uncertain,
                                 self.stopping, max_workers=2)
        self.assertEqual(restored.snapshot(task["id"])["status"], "uncertain")
        self.assertEqual(restored.snapshot(task["id"])["counts"], {"uncertain": 1})
        self.assertEqual(self.deliveries, [])


if __name__ == "__main__":
    unittest.main()
