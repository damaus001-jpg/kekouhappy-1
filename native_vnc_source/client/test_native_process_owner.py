import os
import subprocess
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
from native_process_owner import ProcessOwner,terminate_tree


class FakeJob:
    def __init__(self):self.members=[];self.closed=False
    def add(self,pid):self.members.append(pid)
    def close(self):self.closed=True


class OwnerTests(unittest.TestCase):
    def test_disconnect_cancels_old_ticket_without_stopping_other_phone(self):
        job=FakeJob();killed=Mock();owner=ProcessOwner(job=job,terminate=killed)
        old_ticket=owner.ticket('phone-a')
        a=SimpleNamespace(pid=123456,poll=lambda:None)
        b=SimpleNamespace(pid=123457,poll=lambda:None)
        owner.spawn(lambda:a,tag='phone-a',ticket=old_ticket)
        owner.spawn(lambda:b,tag='phone-b',ticket=owner.ticket('phone-b'))
        owner.stop_tag('phone-a')
        killed.assert_called_once_with(123456)
        self.assertIn(123457,owner.processes)
        factory=Mock(return_value=a)
        with self.assertRaises(RuntimeError):owner.spawn(factory,tag='phone-a')
        owner.resume_tag('phone-a')
        with self.assertRaises(RuntimeError):owner.spawn(factory,tag='phone-a',ticket=old_ticket)
        factory.assert_not_called()
        owner.spawn(factory,tag='phone-a',ticket=owner.ticket('phone-a'))
        owner.close()

    def test_late_spawn_after_shutdown_never_calls_factory(self):
        job=FakeJob();owner=ProcessOwner(job=job)
        owner.close()
        factory=Mock()
        with self.assertRaises(RuntimeError):owner.spawn(factory)
        factory.assert_not_called()
        self.assertTrue(job.closed)

    def test_close_racing_with_creation_waits_for_ownership_registration(self):
        job=FakeJob();owner=ProcessOwner(job=job)
        entered=threading.Event();release=threading.Event()
        def factory():
            entered.set();release.wait(3)
            return SimpleNamespace(pid=456)
        spawn=threading.Thread(target=lambda:owner.spawn(factory))
        spawn.start();self.assertTrue(entered.wait(2))
        closer=threading.Thread(target=owner.close)
        closer.start();release.set()
        spawn.join(3);closer.join(3)
        self.assertFalse(spawn.is_alive());self.assertFalse(closer.is_alive())
        self.assertEqual(job.members,[456]);self.assertTrue(job.closed)
        with self.assertRaises(RuntimeError):owner.adopt(789)

    @unittest.skipUnless(os.name=='nt','Windows Job integration')
    def test_real_job_closes_parent_and_venv_descendants(self):
        owner=ProcessOwner()
        code="import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); print(p.pid,flush=True); time.sleep(60)"
        parent=None
        child_pid=None
        try:
            parent=owner.spawn(lambda:subprocess.Popen([sys.executable,'-c',code],
                stdout=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW|0x00000004),suspended=True)
            self.assertFalse(owner.unassigned,str((owner.job_error,owner.assignment_errors)))
            child_pid=int(parent.stdout.readline().strip())
            child=psutil.Process(child_pid)
            owner.close()
            parent.wait(timeout=5)
            _,alive=psutil.wait_procs([child],timeout=5)
            self.assertFalse(alive,'A descendant survived closing the Job')
        finally:
            owner.close()
            if parent:
                terminate_tree(parent.pid)
                parent.wait(timeout=5)
                if parent.stdout:parent.stdout.close()
            if child_pid:terminate_tree(child_pid)


if __name__=='__main__':unittest.main()
