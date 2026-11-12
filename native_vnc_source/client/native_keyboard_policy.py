"""Prepare hardware keyboard before touches; desktop editing keys work in any field."""
import asyncio
import ctypes
from ctypes import wintypes
import logging


def host_clipboard_text():
    user=ctypes.WinDLL('user32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    user.OpenClipboard.argtypes=[wintypes.HWND]
    user.GetClipboardData.argtypes=[wintypes.UINT]
    user.GetClipboardData.restype=wintypes.HANDLE
    kernel.GlobalLock.argtypes=[wintypes.HANDLE]
    kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[wintypes.HANDLE]
    kernel.GlobalSize.argtypes=[wintypes.HANDLE]
    kernel.GlobalSize.restype=ctypes.c_size_t
    if not user.OpenClipboard(None):raise ValueError('电脑剪贴板正在被占用，请重试')
    try:
        handle=user.GetClipboardData(13)
        if not handle:raise ValueError('电脑剪贴板没有文字')
        size=kernel.GlobalSize(handle)
        if not 0<size<=4*1024*1024:raise ValueError('电脑剪贴板文字过长')
        pointer=kernel.GlobalLock(handle)
        if not pointer:raise ValueError('无法读取电脑剪贴板')
        try:return ctypes.wstring_at(pointer,size//2).split('\x00',1)[0]
        finally:kernel.GlobalUnlock(handle)
    finally:user.CloseClipboard()


def install_keyboard_policy(server_class,clipboard_reader=host_clipboard_text,control_allowed=lambda:True):
    if getattr(server_class,'_desktop_keyboard_policy',False):return
    original_pointer=server_class._handle_pointer
    original_key=server_class._handle_key
    original_cut_text=getattr(server_class,'_handle_cut_text',None)
    original_client=getattr(server_class,'_handle_client',None)
    original_stop_hid=getattr(server_class,'_stop_hid',None)
    logger=logging.getLogger('vnc_external_keyboard')
    async def warm(self):
        await self._ensure_keyboard()
        if not getattr(self,'_keyboard_warmed',False):
            await self._uhs.send_keyboard(self._kb_service_id,set())
            self._keyboard_warmed=True
            logger.info('external keyboard ready before input focus')
    async def pointer(self,client,button_mask,x,y):
        if not control_allowed():
            if getattr(client,'pressed',False) or getattr(client,'last_button_mask',0):
                await original_pointer(self,client,0,x,y)
            await release_keys(self,client)
            return
        if button_mask&1:
            try:await warm(self)
            except Exception as exc:
                logger.warning('input click held: external keyboard not ready: %s',exc)
                return
        await original_pointer(self,client,button_mask,x,y)
    async def key(self,client,keysym,down):
        if not control_allowed():
            await release_keys(self,client)
            return
        editing=getattr(client,'_desktop_edit_keys',set())
        if not down and keysym in editing:
            editing.discard(keysym)
            return
        letter=chr(keysym).lower() if 0x20<=keysym<=0x7e else ''
        if down and client.mod_ctrl and letter in ('a','c','v','x','z','y'):
            try:
                await warm(self)
                if letter=='v':
                    text=await asyncio.to_thread(clipboard_reader)
                    if not text:raise ValueError('电脑剪贴板没有文字')
                    if self._clipboard_monitor is None:raise ValueError('手机剪贴板服务未就绪')
                    await self._clipboard_monitor.set_text(text)
                    await asyncio.sleep(.3)
                usages={0xe3}  # iOS editing shortcuts use Command, not Control.
                if client.mod_shift or letter=='y':usages.add(0xe1)
                mapped='z' if letter=='y' else letter
                usages.add(4+ord(mapped)-ord('a'))
                try:await self._uhs.send_keyboard(self._kb_service_id,usages)
                finally:await self._uhs.send_keyboard(self._kb_service_id,set())
                editing.add(keysym)
                client._desktop_edit_keys=editing
            except Exception as exc:
                logger.warning('desktop edit shortcut failed: %s',exc)
            return
        await original_key(self,client,keysym,down)
    async def release_keys(self,client):
        if getattr(client,'pressed_keys',set()) and getattr(self,'_kb_service_id',None) is not None:
            await self._uhs.send_keyboard(self._kb_service_id,set())
            client.pressed_keys.clear()
        for attribute in ('mod_ctrl','mod_shift','mod_alt','mod_cmd'):
            if hasattr(client,attribute):setattr(client,attribute,False)
        for attribute in ('active_typing','_desktop_edit_keys'):
            value=getattr(client,attribute,None)
            if value is not None:value.clear()
        combos=getattr(client,'active_combos',{})
        for mapping in list(combos.values()):
            await self._send_hid_button(mapping[0],mapping[1],down=False)
        combos.clear()
    async def cut_text(self,*args,**kwargs):
        if control_allowed():await original_cut_text(self,*args,**kwargs)
    async def check_locked(self):
        clients=list(getattr(self,'_clients',()))
        held=[c for c in clients if getattr(c,'pressed',False) or getattr(c,'last_button_mask',0)
              or getattr(c,'pressed_keys',set()) or getattr(c,'active_combos',{})]
        if not held or control_allowed():return
        for client in held:
            if getattr(client,'pressed',False) or getattr(client,'last_button_mask',0):
                await original_pointer(self,client,0,0,0)
            await release_keys(self,client)
    async def watch(self):
        while True:
            await asyncio.sleep(.2)
            try:await check_locked(self)
            except Exception as exc:logger.warning('control-lock release failed: %s',exc)
    async def handle_client(self,*args,**kwargs):
        task=getattr(self,'_desktop_control_guard',None)
        if task is None or task.done():self._desktop_control_guard=asyncio.create_task(watch(self))
        return await original_client(self,*args,**kwargs)
    async def stop_hid(self):
        try:await original_stop_hid(self)
        finally:self._keyboard_warmed=False
    server_class._handle_pointer=pointer
    server_class._handle_key=key
    if original_cut_text is not None:server_class._handle_cut_text=cut_text
    if original_client is not None:server_class._handle_client=handle_client
    if original_stop_hid is not None:server_class._stop_hid=stop_hid
    server_class._check_desktop_control_lock=check_locked
    server_class._desktop_keyboard_policy=True
