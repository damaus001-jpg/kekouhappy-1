import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from controller import screen_tunnel_closed, supervise_screen


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_dialer_requests_restart_instead_of_waiting_forever(self):
        process=type('Process',(),{})()
        process.wait=AsyncMock()
        with patch('controller.asyncio.wait_for',side_effect=asyncio.TimeoutError), \
             patch('controller.screen_tunnel_closed',return_value=True), \
             patch('controller.emit') as emit:
            self.assertEqual(await supervise_screen(process,Path('unused')),1)
        self.assertEqual(emit.call_args.args[0]['status'],'error')

    async def test_natural_process_exit_is_preserved(self):
        process=type('Process',(),{})()
        process.wait=AsyncMock(return_value=7)
        self.assertEqual(await supervise_screen(process,Path('missing')),7)

    async def test_log_probe_only_recovers_permanently_closed_dialer(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'screen.log'
            self.assertFalse(screen_tunnel_closed(path))
            path.write_text('TimeoutError: video startup slow\n')
            self.assertFalse(screen_tunnel_closed(path))
            path.write_text('ConnectionError: userspace dial plane is closed\n')
            self.assertTrue(screen_tunnel_closed(path))
            path.write_text('ConnectionError: userspace dial plane is closed\n'+'x'*9000)
            self.assertFalse(screen_tunnel_closed(path))
