from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from native_keyboard_policy import install_keyboard_policy


class KeyboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_lock_releases_already_held_keys_without_new_input(self):
        class Server:
            async def _handle_pointer(self,*args):pass
            async def _handle_key(self,*args):pass
        install_keyboard_policy(Server,control_allowed=lambda:False)
        server=Server()
        server._kb_service_id=1
        server._uhs=SimpleNamespace(send_keyboard=AsyncMock())
        client=SimpleNamespace(pressed=False,last_button_mask=0,pressed_keys={4},mod_ctrl=False)
        server._clients=[client]
        await server._check_desktop_control_lock()
        server._uhs.send_keyboard.assert_awaited_once_with(1,set())
        self.assertEqual(client.pressed_keys,set())

    async def test_monitor_only_blocks_keys_clicks_and_clipboard_writes(self):
        actions=[]
        class Server:
            async def _ensure_keyboard(self):actions.append('warm')
            async def _handle_pointer(self,*args):actions.append('touch')
            async def _handle_key(self,*args):actions.append('key')
            async def _handle_cut_text(self,*args,**kwargs):actions.append('clipboard')
        install_keyboard_policy(Server,control_allowed=lambda:False)
        server=Server()
        client=SimpleNamespace(pressed=False,last_button_mask=0,pressed_keys=set(),mod_ctrl=False)
        await server._handle_pointer(client,1,0,0)
        await server._handle_key(client,ord('a'),True)
        await server._handle_cut_text(client,b'private text',extended=False)
        self.assertEqual(actions,[])

    def server(self):
        order=[]
        class Server:
            async def _ensure_keyboard(self):order.append('keyboard')
            async def _handle_pointer(self,*args):order.append('touch')
            async def _handle_key(self,*args):order.append('normal-key')
        install_keyboard_policy(Server,clipboard_reader=lambda:'中文\n🙂')
        server=Server()
        server._kb_service_id=1
        server._uhs=SimpleNamespace(send_keyboard=AsyncMock())
        server._clipboard_monitor=SimpleNamespace(set_text=AsyncMock())
        return server,order

    async def test_keyboard_is_ready_before_any_input_touch(self):
        server,order=self.server()
        await server._handle_pointer(SimpleNamespace(),1,30,40)
        self.assertEqual(order,['keyboard','touch'])
        server._uhs.send_keyboard.assert_awaited_once_with(1,set())

    async def test_unready_keyboard_does_not_click_and_raise_software_keyboard(self):
        server,order=self.server()
        server._ensure_keyboard=AsyncMock(side_effect=ValueError('not ready'))
        await server._handle_pointer(SimpleNamespace(),1,30,40)
        self.assertNotIn('touch',order)

    async def test_control_v_uses_unicode_clipboard_and_command_without_return(self):
        server,_=self.server()
        client=SimpleNamespace(mod_ctrl=True,mod_shift=False)
        await server._handle_key(client,ord('v'),True)
        await server._handle_key(client,ord('v'),False)
        server._clipboard_monitor.set_text.assert_awaited_once_with('中文\n🙂')
        reports=[args.args[1] for args in server._uhs.send_keyboard.await_args_list]
        self.assertIn({0xe3,0x19},reports)
        self.assertFalse(any(0x28 in report for report in reports))
        self.assertEqual(reports[-1],set())


if __name__=='__main__':unittest.main()
