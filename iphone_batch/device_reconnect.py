"""Bounded, independent reconnect jobs; never replay phone input."""
import threading
import time
import uuid
import json
import os
import subprocess
import sys
from pathlib import Path

def _run_device_command(device, command, timeout, timeout_message, stopping=None):
    import controller
    import psutil
    if stopping is not None and stopping.is_set():
        raise ValueError('工作台正在关闭，设备恢复已停止')
    process=subprocess.Popen(command,env=controller.device_environment(device['udid']),
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',errors='replace',
        creationflags=0x08000000 if os.name=='nt' else 0)
    deadline=time.monotonic()+timeout
    while True:
        if stopping is not None and stopping.is_set():
            reason='工作台正在关闭，设备恢复已停止'
            break
        remaining=deadline-time.monotonic()
        if remaining<=0:
            reason=timeout_message
            break
        try:
            stdout,stderr=process.communicate(timeout=min(1,remaining))
            return process.returncode,stdout,stderr
        except subprocess.TimeoutExpired:
            continue
    # Windows venv launchers have a real Python child. Never leave a late
    # pairing request or media teardown running after cancellation/timeout.
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
    raise ValueError(reason)


def repair_phone_trust(device, stopping=None):
    """Only explicit page actions use this; normal viewer retries never pair."""
    command=[sys.executable,str(Path(__file__).with_name('device_trust.py')),'--device',device['udid']]
    code,stdout,_=_run_device_command(device,command,90,
        '信任修复超时，请保持手机解锁；若有信任提示，请在手机确认后重试',stopping)
    try:result=json.loads(stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):raise ValueError('信任修复未返回有效结果，请检查手机连接') from None
    if not isinstance(result,dict):raise ValueError('信任修复未返回有效结果，请检查手机连接')
    if code or result.get('ok') is not True:
        raise ValueError(result.get('error') or '信任修复未完成，请检查手机上的提示后重试')
    return result


def reset_phone_session(device, stopping=None):
    import controller
    command=controller.command_for(device['udid'],['developer','core-device','display','reset-workspace-session'])
    code,stdout,stderr=_run_device_command(device,command,28,
        '手机端会话清理超时，请检查 USB 和手机状态后重试',stopping)
    try:result=json.loads(stdout.strip().splitlines()[-1])
    except (ValueError,IndexError):result={}
    if code or not isinstance(result,dict) or result.get('remote_session_reset') is not True or result.get('input_events_sent') is not False:
        detail=(stderr or stdout).strip().splitlines()
        detail='；'.join(line.strip() for line in detail[-2:] if line.strip())[-320:]
        reason=f'，设备返回：{detail}' if detail else ''
        raise ValueError(f'手机端媒体/触控会话清理未确认完成（退出码 {code}）{reason}')
    return result


def reboot_phone(device, stopping, stage=lambda value: None, timeout=150):
    """Send Restart once, then observe this exact USB device go down and return."""
    import controller
    command=controller.command_for(device['udid'],['diagnostics','restart'])
    code,_,_=_run_device_command(device,command,20,
        '重启指令响应超时，手机可能已经重启；请检查手机，未自动重复发送',stopping)
    if code:
        raise ValueError('重启指令未确认成功，请检查手机是否已重启；未自动重复发送')
    stage('waiting_boot')
    deadline=time.monotonic()+timeout
    disconnected=False
    while not stopping.is_set():
        if time.monotonic()>=deadline:
            raise ValueError('等待手机重新接入超时，请检查 USB 并解锁手机；未重复发送重启指令')
        try:
            online=any(row['udid']==device['udid'] for row in controller.discover())
        except (OSError,ValueError,RuntimeError):
            # A usbmux failure is not evidence that the phone rebooted.
            stopping.wait(.5)
            continue
        if not online:disconnected=True
        elif disconnected:return
        stopping.wait(.5)
    raise ValueError('工作台正在关闭，已停止等待手机开机；未重复发送重启指令')

class DeviceReconnects:
    def __init__(self, rebuild, ready, finish, stopping, timeout=75, queued=lambda device:False):
        self.rebuild,self.ready,self.finish=rebuild,ready,finish
        self.stopping,self.timeout=stopping,timeout
        self.queued=queued
        self.lock=threading.Lock()
        self.jobs={}

    def pending(self, udid):
        with self.lock:return self.jobs.get(udid,{}).get('state')=='reconnecting'

    def snapshot(self, udid):
        with self.lock:job=dict(self.jobs.get(udid,{}))
        return {'reconnecting':job.get('state')=='reconnecting',
                'reconnect_operation':job.get('operation','reconnect'),
                'reconnect_state':job.get('state'), 'reconnect_error':job.get('error'), 'reconnect_id':job.get('id'),
                'reconnect_stage':job.get('stage'),
                'reconnect_elapsed':round(time.monotonic()-job['started'],1) if job.get('started') is not None and job.get('state')=='reconnecting' else job.get('elapsed')}

    def stage(self, udid, stage):
        with self.lock:
            if self.jobs.get(udid,{}).get('state')=='reconnecting':self.jobs[udid]['stage']=stage

    def begin(self, device, operation='reconnect'):
        if operation not in ('reconnect','reboot'):raise ValueError('无效的设备操作')
        with self.lock:
            if self.jobs.get(device['udid'],{}).get('state')=='reconnecting':
                if self.jobs[device['udid']].get('operation','reconnect')!=operation:
                    raise ValueError('该手机正在处理设备操作，请完成后重试')
                return self.jobs[device['udid']]['id']
            identifier=uuid.uuid4().hex
            self.jobs[device['udid']]={'state':'reconnecting','id':identifier,'operation':operation,'stage':'stopping','started':time.monotonic()}
        threading.Thread(target=self._run,args=(device,identifier),daemon=True).start()
        return identifier

    def _run(self, device, identifier):
        started=time.monotonic()
        try:
            with self.lock:operation=self.jobs[device['udid']]['operation']
            if operation=='reboot':self.rebuild(device,reboot=True)
            else:self.rebuild(device)
            # Trust confirmation and session cleanup each have their own
            # bounds. Give video readiness its full budget after preparation.
            budget=max(self.timeout,180) if operation=='reboot' else self.timeout
            deadline=time.monotonic()+budget
            waited_for_startup=False
            while not self.stopping.is_set():
                if self.queued(device):
                    # The startup queue owns its CPU/startup deadlines. Do not
                    # report a reconnect failure while that bounded work waits.
                    waited_for_startup=True
                    self.stopping.wait(.25)
                    continue
                if waited_for_startup:
                    deadline=time.monotonic()+budget
                    waited_for_startup=False
                if time.monotonic()>=deadline:
                    raise ValueError('等待重启后连接恢复超时，请检查 USB 并确认手机已开机，再重新连接；未重复重启'
                        if operation=='reboot' else '重新连接超时，请检查 USB 及设备状态后重试')
                if self.ready(device) and self.finish(device):
                    with self.lock:self.jobs[device['udid']].update(state='ready',stage='ready',elapsed=round(time.monotonic()-started,1))
                    return
                self.stopping.wait(.25)
            raise ValueError('工作台正在关闭，重新连接已停止')
        except Exception as error:
            message=str(error) if isinstance(error,(ValueError,RuntimeError)) else '重新连接失败，请检查 USB 后重试'
            with self.lock:self.jobs[device['udid']].update(state='failed',stage='failed',error=message,elapsed=round(time.monotonic()-started,1))
