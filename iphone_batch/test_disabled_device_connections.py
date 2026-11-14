"""Exercise real dashboard connection entry guards without starting main/phones."""
import ast
from pathlib import Path
import unittest
from device_policy import connection_allowed, require_connection


class DisabledConnectionTests(unittest.TestCase):
    def functions(self):
        module = ast.parse(Path(__file__).with_name('dashboard.py').read_text(encoding='utf-8-sig'))
        main = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        names = {'launch_viewer', 'viewer_ready', 'viewer_video_ready', 'rebuild_device'}
        functions = [node for node in main.body if isinstance(node, ast.FunctionDef) and node.name in names]
        context = {'connection_allowed':connection_allowed, 'require_connection':require_connection,
                   'enabled':frozenset(['on'])}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'dashboard_connection_guards', 'exec'), context)
        return context

    def test_disabled_start_never_reaches_subprocess_creation(self):
        context = self.functions()
        device = {'udid':'off'}
        context['launch_viewer'](device)
        self.assertEqual(device['error'], '已手动断开，画面与操作均已关闭')

    def test_disabled_health_never_reaches_network_requests(self):
        context = self.functions()
        for name in ('viewer_ready','viewer_video_ready'):
            self.assertFalse(context[name]({'udid':'off'}))

    def test_disabled_reconnect_never_acquires_locks_or_resets_phone(self):
        context = self.functions()
        with self.assertRaisesRegex(ValueError, '已停用'):
            context['rebuild_device']({'udid':'off'})
