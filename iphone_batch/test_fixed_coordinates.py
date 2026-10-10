import unittest
from unittest.mock import AsyncMock, Mock, patch
from fixed_coordinates import check_layout, tap


class CoordinateTests(unittest.IsolatedAsyncioTestCase):
    async def test_landscape_blocks_clicks(self):
        profile={'screen':{'width':832,'height':1808}}
        with patch('fixed_coordinates.video_size',return_value=(1808,832)):
            with self.assertRaises(ValueError):await check_layout(Mock(),profile,[])

    async def test_visible_keyboard_blocks_clicks_before_video_read(self):
        with patch('fixed_coordinates.video_size') as video:
            with self.assertRaises(ValueError):
                await check_layout(Mock(),{},['Space, Keyboard Key'])
            video.assert_not_called()

    async def test_tap_releases_touch_after_failure(self):
        phone=Mock();phone.base='http://127.0.0.1:8080'
        phone.request.side_effect=[RuntimeError('contact failed'),{}]
        with patch('fixed_coordinates.asyncio.sleep',AsyncMock()):
            with self.assertRaises(RuntimeError):await tap(phone,{'x':.5,'y':.75})
        calls=phone.request.call_args_list
        self.assertEqual(calls[0].args[2],{'type':'contact','x':32768,'y':49151})
        self.assertEqual(calls[1].args[2],{'type':'release','x':32768,'y':49151})


if __name__=='__main__':unittest.main()
