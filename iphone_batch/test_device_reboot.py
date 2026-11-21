"""Reboot paths with mocked USB/processes only; never restart a real phone."""
import ast
import io
import json
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from device_reconnect import reboot_phone, DeviceReconnects


class RebootCommandTests(unittest.TestCase):
    def test_sends_once_and_waits_for_the_exact_device_to_disconnect_and_return(self):
        stopping=Mock();stopping.is_set.return_value=False
        target={'udid':'target'};stage=Mock()
        with patch('device_reconnect._run_device_command',return_value=(0,'','')) as run, \
                patch('controller.discover',side_effect=[
                    [{'udid':'target'}], [{'udid':'other'}], [{'udid':'other'},{'udid':'target'}]]):
            reboot_phone(target,stopping,stage)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0],target)
        self.assertEqual(run.call_args.args[1][-2:],['diagnostics','restart'])
        stage.assert_called_once_with('waiting_boot')

    def test_command_error_or_timeout_never_replays_restart(self):
        for result in [(1,'','denied'),TimeoutError('lost response')]:
            with self.subTest(result=result), patch('device_reconnect._run_device_command') as run, \
                    patch('controller.discover') as discover:
                if isinstance(result,Exception):run.side_effect=result
                else:run.return_value=result
                with self.assertRaises((ValueError,TimeoutError)):
                    reboot_phone({'udid':'target'},threading.Event())
                run.assert_called_once();discover.assert_not_called()

    def test_usbmux_error_does_not_count_as_device_disconnection(self):
        stopping=Mock();stopping.is_set.return_value=False
        with patch('device_reconnect._run_device_command',return_value=(0,'','')) as run, \
                patch('controller.discover',side_effect=[OSError('usbmux unavailable'),[{'udid':'target'}]]) as discover, \
                patch('device_reconnect.time.monotonic',side_effect=[0,0,0,2]):
            with self.assertRaisesRegex(ValueError,'等待手机重新接入超时'):
                reboot_phone({'udid':'target'},stopping,timeout=1)
            run.assert_called_once();self.assertEqual(discover.call_count,2)

    def test_duplicate_job_never_restarts_twice_and_conflicting_reconnect_is_rejected(self):
        entered=threading.Event();release=threading.Event();completed=threading.Event()
        def rebuild(device,reboot=False):
            self.assertEqual(device['udid'],'target');self.assertTrue(reboot)
            entered.set();release.wait(2)
        finish=Mock(side_effect=lambda _:completed.set() or True)
        jobs=DeviceReconnects(rebuild,lambda _:True,finish,threading.Event())
        try:
            identifier=jobs.begin({'udid':'target'},operation='reboot')
            self.assertTrue(entered.wait(1))
            self.assertEqual(jobs.begin({'udid':'target'},operation='reboot'),identifier)
            self.assertFalse(jobs.pending('other'))
            self.assertEqual(jobs.snapshot('target')['reconnect_operation'],'reboot')
            with self.assertRaisesRegex(ValueError,'正在处理'):
                jobs.begin({'udid':'target'})
        finally:release.set()
        self.assertTrue(completed.wait(1))
        finish.assert_called_once()


class RebootRouteTests(unittest.TestCase):
    def fixture(self,body,allowed=True,readonly=False):
        tree=ast.parse(Path(__file__).with_name('dashboard.py').read_text(encoding='utf-8-sig'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        handler=next(n for n in main.body if isinstance(n,ast.ClassDef) and n.name=='Handler')
        method=next(n for n in handler.body if isinstance(n,ast.FunctionDef) and n.name=='do_POST')
        target={'udid':'target'}
        namespace=dict(json=json,devices=[target,{'udid':'other'}],enabled=None,trust_pending=set(),
            require_connection=Mock(),require_control=Mock(side_effect=ValueError('仅监看') if readonly else None),
            reconnects=SimpleNamespace(begin=Mock(return_value='job')))
        exec(compile(ast.Module(body=[method],type_ignores=[]),'reboot_route','exec'),namespace)
        payload=json.dumps(body).encode()
        request=SimpleNamespace(path='/api/devices/reboot',allowed=lambda:allowed,
            headers={'Content-Length':str(len(payload))},connection=SimpleNamespace(settimeout=Mock()),
            rfile=io.BytesIO(payload),respond=Mock())
        namespace['do_POST'](request)
        return namespace,request

    def test_exact_confirmation_required_and_target_is_pinned(self):
        for body in ({'device':'target'},{'device':'target','confirm':'other'},
                {'device':'missing','confirm':'missing'}):
            state,request=self.fixture(body)
            self.assertEqual(request.respond.call_args.args[0],400)
            state['reconnects'].begin.assert_not_called()
        state,request=self.fixture({'device':'target','confirm':'target'})
        self.assertEqual(request.respond.call_args.args[0],202)
        state['reconnects'].begin.assert_called_once_with({'udid':'target'},operation='reboot')

    def test_unauthorized_and_readonly_cannot_reboot(self):
        for options in ({'allowed':False},{'readonly':True}):
            state,request=self.fixture({'device':'target','confirm':'target'},**options)
            self.assertIn(request.respond.call_args.args[0],(400,403))
            state['reconnects'].begin.assert_not_called()


class RebootDiscoveryTests(unittest.TestCase):
    def test_refresh_retains_rebooting_device_and_selection_but_removes_unplugged_other(self):
        from device_registry import DeviceRegistry
        tree=ast.parse(Path(__file__).with_name('dashboard.py').read_text(encoding='utf-8-sig'))
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        refresh=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='refresh_connected_devices')
        target={'udid':'target','port':8080,'name':'one'}
        other={'udid':'other','port':8081,'name':'two'}
        unplugged={'udid':'unplugged','port':8082,'name':'three'}
        devices=[target,other,unplugged]
        registry=DeviceRegistry(devices)
        manager=SimpleNamespace(lock=threading.Lock(),active=None,selected='target')
        context=dict(controller=SimpleNamespace(discover=lambda:[{'udid':'other'}]),registry=registry,
            workspace_service=SimpleNamespace(phone_lock=threading.Lock()),manager=manager,devices=devices,
            notification_monitor=SimpleNamespace(update_devices=Mock()),trust_pending=set(),
            reconnects=SimpleNamespace(pending=lambda udid:udid=='target',snapshot=lambda _:{'reconnect_operation':'reboot'}),
            startup_queue=SimpleNamespace(pending=lambda _:False,cancel=Mock()),stop_viewer=Mock(),
            children={'other':SimpleNamespace(poll=lambda:None)},input_readiness_lock=threading.Lock(),input_readiness={},
            retry_policy=SimpleNamespace(reset=Mock()),launch_viewer=Mock())
        exec(compile(ast.Module(body=[refresh],type_ignores=[]),'reboot_discovery','exec'),context)
        result=context['refresh_connected_devices']()
        self.assertEqual({d['udid'] for d in devices},{'target','other'})
        self.assertEqual(manager.selected,'target')
        self.assertEqual(result['removed'],1)
        context['stop_viewer'].assert_called_once_with(unplugged)
        context['launch_viewer'].assert_not_called()


if __name__=='__main__':unittest.main()
