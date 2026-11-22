import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import native_workspace


class SmsCampaignNativeSendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task_id = "a" * 32
        self.path = (self.root / "workspace" / "sms-tasks" / self.task_id / "items" / "00000.json")
        self.path.parent.mkdir(parents=True)
        self.record = {"version": 1, "task_id": self.task_id, "index": 0,
                       "device": "phone-a", "number": "+15550000001",
                       "text": "Hello", "status": "ready"}
        self.path.write_text(json.dumps(self.record), encoding="utf-8")
        self.selected = {"phone_number": "+15550000001", "messages": [],
                         "raw_elements": [
                             {"caption": "+15550000001, Show Conversation Details, Button"},
                             {"caption": "Message"}]}
        self.prepared_page = [{"caption": "Message, Hello"}, {"caption": "Send, Button"}]
        self.after = {"phone_number": "+15550000001",
                      "messages": [{"side": "outgoing", "text": "Hello"}],
                      "raw_elements": [{"caption": "Your Message, Hello"}]}
        self.phone = MagicMock()
        self.phone.chord = AsyncMock()
        self.phone.paste = AsyncMock()
        self.phone.keys = AsyncMock()
        self.taps = []
    async def execute(self, *, selected=None, after=None):
        opening = AsyncMock(return_value=(selected or self.selected)["raw_elements"])
        reading = AsyncMock(side_effect=[ValueError("当前会话未读到可确认的消息，未发送"), after or self.after])
        async def tap(_phone, point):
            self.taps.append(point)
            if point == {"x": 0.8, "y": 0.9}:
                state = json.loads(self.path.read_text(encoding="utf-8"))
                self.assertEqual(state["status"], "send_requested")
        with patch.object(native_workspace, "ROOT", self.root), \
             patch.object(native_workspace, "NativeConversation", return_value=self.phone), \
             patch.object(native_workspace, "raw_page", new=AsyncMock(return_value=self.prepared_page)), \
             patch.object(native_workspace, "enter_compose_recipient", new=opening), \
             patch.object(native_workspace, "input_point", return_value={"x": 0.4, "y": 0.9}), \
             patch.object(native_workspace, "send_point", return_value={"x": 0.8, "y": 0.9}), \
             patch.object(native_workspace, "tap", new=AsyncMock(side_effect=tap)), \
             patch.object(native_workspace, "read", new=reading), \
             patch.object(native_workspace.asyncio, "sleep", new=AsyncMock()):
            service = object()
            result = await native_workspace.send_task_unit(
                service, SimpleNamespace(device="phone-a", base="fixture"), self.path)
        opening.assert_awaited_once_with(service, self.phone, "+15550000001", verify_selection=True)
        return result

    async def test_exact_recipient_body_and_durable_marker_precede_single_send_tap(self):
        result = await self.execute()
        self.assertEqual(result["status"], "sent_verified")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["status"], "sent_verified")
        self.assertEqual(self.taps, [{"x": 0.4, "y": 0.9}, {"x": 0.8, "y": 0.9}])
        self.assertEqual([call.args[0] for call in self.phone.paste.await_args_list], ["Hello"])

    async def test_recipient_mismatch_stops_before_message_or_send(self):
        wrong = {**self.selected, "raw_elements": [
            {"caption": "+15550000002, Show Conversation Details, Button"},
            {"caption": "Message"}]}
        with self.assertRaisesRegex(ValueError, "完全匹配"):
            await self.execute(selected=wrong)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["status"], "ready")
        self.assertEqual(self.taps, [])
        self.phone.paste.assert_not_awaited()

    async def test_missing_receipt_stays_uncertain_after_one_send_tap(self):
        missing_receipt = {"phone_number": "+15550000001", "messages": [],
                           "raw_elements": [{"caption": "Send, Button"}]}
        with self.assertRaisesRegex(RuntimeError, "发送结果未确认"):
            await self.execute(after=missing_receipt)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["status"], "send_requested")
        self.assertEqual(self.taps.count({"x": 0.8, "y": 0.9}), 1)


if __name__ == "__main__":
    unittest.main()
