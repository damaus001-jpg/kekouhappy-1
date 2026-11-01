import unittest
from unittest.mock import patch, AsyncMock
from controller import ensure_screen_services


class ScreenPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_mode_never_mounts_or_starts_video(self):
        with patch('controller.screen_service_command',AsyncMock(return_value=(0,'false',''))) as command:
            with self.assertRaisesRegex(RuntimeError,'开发者模式未开启'):
                await ensure_screen_services('phone')
            self.assertEqual(command.await_count,1)

    async def test_ready_phone_does_not_mount_again(self):
        with patch('controller.screen_service_command',AsyncMock(side_effect=[(0,'true',''),(0,'media','')])) as command:
            await ensure_screen_services('phone')
            self.assertEqual(command.await_count,2)

    async def test_missing_media_services_mount_then_verify(self):
        results=[(0,'true',''),(1,'','missing display service'),(0,'',''),(0,'media','')]
        with patch('controller.screen_service_command',AsyncMock(side_effect=results)) as command:
            await ensure_screen_services('phone')
            self.assertEqual(command.await_args_list[2].args[1],['mounter','auto-mount'])
            self.assertEqual(command.await_count,4)

    async def test_mount_failure_is_not_reported_as_ready(self):
        with patch('controller.screen_service_command',AsyncMock(side_effect=[(0,'true',''),(1,'','missing'),(1,'','offline')])):
            with self.assertRaisesRegex(RuntimeError,'镜像准备失败'):
                await ensure_screen_services('phone')
