"""One reusable AX connection for the currently active 8070 foreground phone."""
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
import threading
import time
from pairing_patch import PhoneTrustRequired


class ForegroundAXSession:
    def __init__(self, root, device):
        self.root, self.device = root, device
        self.ready = threading.Event()
        self.call_lock = threading.Lock()
        self.loop = None
        self.thread = threading.Thread(target=self._thread_main, name='foreground-ax-session', daemon=True)
        self.error = None
        self.lockdown = None
        self.audit = None
        self.closing = threading.Event()
        self.thread.start()
        if not self.ready.wait(10):
            self.close()
            raise TimeoutError('原生号码识别连接初始化超时')
        if self.error:
            self.close()
            if isinstance(self.error, PhoneTrustRequired):
                raise self.error
            raise RuntimeError('原生号码识别连接初始化失败：' + self.error)

    def _thread_main(self):
        loop_type = getattr(asyncio, 'WindowsSelectorEventLoop', asyncio.SelectorEventLoop)
        self.loop = loop_type()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(asyncio.wait_for(self._open(), 8))
        except BaseException as error:
            self.error = error if isinstance(error, PhoneTrustRequired) else type(error).__name__
            try:
                self.loop.run_until_complete(self._close_services())
            finally:
                self.loop.close()
                self.ready.set()
            return
        self.ready.set()
        try:
            if not self.closing.is_set():
                self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self._close_services())
            self.loop.close()

    async def _open(self):
        from pathlib import Path
        from pymobiledevice3 import common
        from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
        from pairing_patch import open_paired_usb
        data = Path(self.root)
        common._HOMEFOLDER = data
        self.lockdown = await open_paired_usb(self.device, data)
        self.audit = AccessibilityAudit(self.lockdown)
        await self.audit.__aenter__()

    async def _close_services(self):
        audit, lockdown = self.audit, self.lockdown
        self.audit = self.lockdown = None
        if audit is not None:
            try:
                await asyncio.wait_for(audit.__aexit__(None, None, None), 2)
            except BaseException:
                pass
        if lockdown is not None:
            try:
                await asyncio.wait_for(lockdown.close(), 2)
            except BaseException:
                pass

    async def _invoke(self, action, options, cancelled, finished):
        from native_foreground import probe_title, read_window, read_sent_tail
        if action == 'auto_probe':
            operation = probe_title(self.audit, recover_first=options.get('recover_first', False))
        elif action == 'auto_read':
            from ax_conversation import capture_conversation
            operation = capture_conversation(self.audit, {**options, 'device': self.device})
        elif action == 'auto_sent_tail':
            operation = read_sent_tail(self.audit, options)
        else:
            operation = read_window(self.audit, options, tail=action == 'auto_tail')
        task = asyncio.create_task(operation)
        try:
            while not task.done():
                if cancelled():
                    task.cancel()
                await asyncio.wait((task,), timeout=.025)
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            finished.set()

    def call(self, action, options, cancelled):
        from foreground_reader import ReadingCancelled
        with self.call_lock:
            if cancelled():
                raise ReadingCancelled()
            if self.closing.is_set() or self.error or not self.thread.is_alive() or self.loop is None:
                raise RuntimeError('原生号码识别连接已断开')
            finished = threading.Event()
            future = asyncio.run_coroutine_threadsafe(self._invoke(action, options, cancelled, finished), self.loop)
            deadline = time.monotonic() + 70
            try:
                while True:
                    if cancelled() or self.closing.is_set():
                        raise ReadingCancelled()
                    if time.monotonic() >= deadline:
                        raise TimeoutError('自动读取超时')
                    try:
                        return future.result(timeout=.025)
                    except FutureTimeout:
                        if future.done():
                            raise
            except BaseException as error:
                future.cancel()
                # Do not hand phone_lock back while AX cancellation is still cleaning up.
                if not finished.wait(1) or not isinstance(error, ReadingCancelled):
                    self.error = type(error).__name__
                    cleanup = asyncio.run_coroutine_threadsafe(self._close_services(), self.loop)
                    try:
                        cleanup.result(timeout=5)
                    except BaseException:
                        cleanup.cancel()
                raise

    def close(self):
        self.closing.set()
        if self.loop is None:
            if self.thread.is_alive():
                self.thread.join(timeout=2)
            return
        if self.thread.is_alive() and self.loop.is_running():
            with self.call_lock:
                future = asyncio.run_coroutine_threadsafe(self._close_services(), self.loop)
                try:
                    future.result(timeout=5)
                except BaseException:
                    future.cancel()
                self.loop.call_soon_threadsafe(self.loop.stop)
        if threading.current_thread() is not self.thread:
            self.thread.join(timeout=5)
