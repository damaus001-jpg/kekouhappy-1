"""Readiness must survive continuous confirmed input, without extending stale holds."""
import ast
import threading
import time
import unittest
from concurrent.futures import Future
from pathlib import Path


class InputReadinessTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse(Path(__file__).with_name('dashboard.py').read_text(encoding='utf-8-sig'))
        main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
        functions=[node for node in main.body if isinstance(node,ast.FunctionDef)
                   and node.name in ('record_input_readiness','input_readiness_snapshot')]
        self.values={}
        self.scope={'time':time,'input_readiness':self.values,'input_readiness_lock':threading.Lock(),
                    'generations':{},'control_allowed':lambda device:True}
        exec(compile(ast.Module(body=functions,type_ignores=[]),'readiness','exec'),self.scope)

    def record(self,result):
        future=Future();future.set_result(result)
        self.scope['record_input_readiness']('one',future)
        return self.scope['input_readiness_snapshot']('one')

    def test_repeated_drag_keeps_control_ready_after_idle_probe_expires(self):
        self.values['one']={'ready':True,'last_success':time.monotonic()-45,'checked_at':time.monotonic()-1}
        result=self.record({'state':'busy','input_confirmed_age':.2})
        self.assertTrue(result['control_ready'])

    def test_old_or_unconfirmed_hold_does_not_extend_readiness(self):
        for age in [None,45,-1,True,float('nan'),float('inf'),'0']:
            with self.subTest(age=age):
                self.values['one']={'ready':True,'last_success':time.monotonic()-45}
                result=self.record({'state':'busy','input_confirmed_age':age})
                self.assertFalse(result['control_ready'])

    def test_failed_probe_blocks_control_even_after_recent_success(self):
        self.record({'ok':True,'state':'ready'})
        self.assertFalse(self.record({'ok':False,'state':'unavailable'})['control_ready'])


if __name__=='__main__':unittest.main()
