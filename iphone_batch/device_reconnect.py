"""Bounded, independent reconnect jobs; never replay phone input."""
import threading
import time
import uuid
import json
import os
import subprocess

def reset_phone_session(device):
    import controller
    import psutil
    command=controller.command_for(device['udid'],['developer','core-device','display','reset-workspace-session'])
    process=subprocess.Popen(command,env=controller.device_environment(device['udid']),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',
        creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        stdout,_=process.communicate(timeout=28)
    except subprocess.TimeoutExpired:
        # Windows venv launchers have a real Python child. Stop the diagnostic
        # process tree as well, so a timeout cannot leave a late media teardown.
        try:
            parent=psutil.Process(process.pid)
            descendants=parent.children(recursive=True)
            for child in reversed(descendants):
                if child.name().lower().startswith('python'):
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
        except psutil.NoSuchProcess:pass
        if process.poll() is None:process.kill()
        process.communicate(timeout=3)
        raise ValueError('手机端会话清理超时，请检查 USB 和手机状态后重试') from None
    try:result=json.loads(stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):result={}
    if process.returncode or result.get('remote_session_reset') is not True or result.get('input_events_sent') is not False:
        raise ValueError('手机端媒体/触控会话清理未确认完成，请检查连接后重试')
    return result

class DeviceReconnects:
    def __init__(self, rebuild, ready, finish, stopping, timeout=75):
        self.rebuild,self.ready,self.finish=rebuild,ready,finish
        self.stopping,self.timeout=stopping,timeout
        self.lock=threading.Lock()
        self.jobs={}

    def pending(self, udid):
        with self.lock:return self.jobs.get(udid,{}).get('state')=='reconnecting'

    def snapshot(self, udid):
        with self.lock:job=dict(self.jobs.get(udid,{}))
        return {'reconnecting':job.get('state')=='reconnecting',
                'reconnect_state':job.get('state'), 'reconnect_error':job.get('error'), 'reconnect_id':job.get('id'),
                'reconnect_stage':job.get('stage'),
                'reconnect_elapsed':round(time.monotonic()-job['started'],1) if job.get('started') is not None and job.get('state')=='reconnecting' else job.get('elapsed')}

    def stage(self, udid, stage):
        with self.lock:
            if self.jobs.get(udid,{}).get('state')=='reconnecting':self.jobs[udid]['stage']=stage

    def begin(self, device):
        with self.lock:
            if self.jobs.get(device['udid'],{}).get('state')=='reconnecting':
                return self.jobs[device['udid']]['id']
            identifier=uuid.uuid4().hex
            self.jobs[device['udid']]={'state':'reconnecting','id':identifier,'stage':'stopping','started':time.monotonic()}
        threading.Thread(target=self._run,args=(device,identifier),daemon=True).start()
        return identifier

    def _run(self, device, identifier):
        started=time.monotonic()
        try:
            deadline=started+self.timeout
            self.rebuild(device)
            while not self.stopping.is_set():
                if time.monotonic()>=deadline:
                    raise ValueError('重新连接超时，请检查 USB、手机解锁及设备状态后重试')
                if self.ready(device) and self.finish(device):
                    with self.lock:self.jobs[device['udid']].update(state='ready',stage='ready',elapsed=round(time.monotonic()-started,1))
                    return
                self.stopping.wait(.25)
            raise ValueError('工作台正在关闭，重新连接已停止')
        except Exception as error:
            message=str(error) if isinstance(error,(ValueError,RuntimeError)) else '重新连接失败，请检查 USB 后重试'
            with self.lock:self.jobs[device['udid']].update(state='failed',stage='failed',error=message,elapsed=round(time.monotonic()-started,1))
