"""Install, validate and uninstall the 8070 EXE in an isolated Chinese path."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime
import winreg

ROOT=Path(__file__).resolve().parents[1]
KEY=r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7C9E926A-5F26-4BF4-A17E-D74080701800}_is1'

BACKEND_CHECK=r'''
import json, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
import psutil
import backend_control as control
output=Path(sys.argv[1])
with tempfile.TemporaryDirectory(dir=output.parent) as folder:
    root=Path(folder); scripts=root/'iphone_batch';scripts.mkdir()
    (scripts/'controller.py').write_text('import time; time.sleep(120)',encoding='utf-8')
    (scripts/'dashboard.py').write_text("import subprocess,sys,time\nfrom pathlib import Path\nchild=subprocess.Popen([sys.executable,str(Path(__file__).with_name('controller.py'))],creationflags=0x08000000)\nPath(__file__).with_name('child.pid').write_text(str(child.pid))\ntime.sleep(120)\n",encoding='utf-8')
    backend=control.Backend();child=None
    with patch.object(control,'PROJECT',root),patch.object(control,'SCRIPTS',scripts),patch.object(control,'LOGS',root/'logs'),patch.object(backend,'_ensure_tunneld'),patch.object(backend,'_stop_tunneld'),patch.object(backend,'_tunneld_is_owned',return_value=False):
        try:
            started=backend.start()
            deadline=time.monotonic()+10
            while not (scripts/'child.pid').exists() and time.monotonic()<deadline:time.sleep(.1)
            child=psutil.Process(int((scripts/'child.pid').read_text()))
            assert '运行中' in backend.status()
            stopped=backend.stop()
            assert '全部关闭' in stopped and not child.is_running() and not backend.processes()
            assert backend.started.poll() is not None
        finally:
            backend.stop()
            if child and child.is_running():child.kill();child.wait(5)
output.write_text(json.dumps({'ok':True,'start':started,'stop':stopped,'parent_and_child_stopped':True,'real_phone_or_tunnel_started':False},ensure_ascii=False,indent=2),encoding='utf-8')
'''

def run(args,env=None,timeout=900):
    subprocess.run([str(x) for x in args],env=env,check=True,timeout=timeout,creationflags=0x08000000)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('installer',type=Path)
    parser.add_argument('--language', choices=('chinesesimp','english'), default='chinesesimp')
    args=parser.parse_args()
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive,KEY,0,winreg.KEY_READ|view):
                    raise RuntimeError('Existing 8070 installation: refusing to replace its registration')
            except FileNotFoundError:pass
    version=(ROOT/'VERSION').read_text(encoding='utf-8-sig').strip()
    validation=ROOT/'iphone_batch/.device-data/installer-validation'/('8070-'+version+'-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    target=validation/'独立 安装目录'
    if target.exists():raise RuntimeError('Validation directory already exists')
    validation.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    for key in ('PYTHONHOME','PYTHONPATH','ELECTRON_RUN_AS_NODE'):env.pop(key,None)
    env.update(PATH=str(Path(os.environ['SystemRoot'])/'System32'),LOCALAPPDATA=str(validation/'fresh-user'),PYTHONUTF8='1')
    report={'version':version,'language':args.language,'relocated_install':False,'uninstalled':False}
    try:
        run([args.installer.resolve(),'/LANG='+args.language,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/MERGETASKS=!desktopicon','/DIR='+str(target),'/LOG='+str(validation/'install.log')],env)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as uninstall_registry:
            display_name=winreg.QueryValueEx(uninstall_registry,'DisplayName')[0]
        expected_name='皮卡丘手机工作台' if args.language=='chinesesimp' else 'Pikachu Phone Workbench'
        if expected_name not in display_name or '8070' in display_name:
            raise RuntimeError('Incorrect localized installation name: '+display_name)
        if not (target/'workbench.ico').is_file():raise RuntimeError('Missing brand icon')
        report['display_name']=display_name
        host_only=(target/'8070-host-policy.json').is_file()
        if host_only:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\PhoneWorkbench8070',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as registry:
                registered=Path(winreg.QueryValueEx(registry,'InstallDir')[0])
                protocol=winreg.QueryValueEx(registry,'ControlProtocol')[0]
            if registered.resolve()!=target.resolve() or protocol!=1:raise RuntimeError('Invalid installation discovery registry')
            if (target/'client').exists() or (target/'PhoneWorkbench8070.exe').exists():raise RuntimeError('Standalone entry leaked into host-only installation')
            command=[target/'runtime/python.exe',target/'tools/check_8070_install.py','--output',validation/'runtime.json']
        else:command=[target/'PhoneWorkbench8070.exe','--check-install',validation/'runtime.json']
        run(command,env,150)
        result=json.loads((validation/'runtime.json').read_text(encoding='utf-8'))
        if not result.get('ok'):raise RuntimeError(str(result))
        run([target/'runtime/python.exe','-c',BACKEND_CHECK,validation/'backend-control.json'],env,45)
        backend=json.loads((validation/'backend-control.json').read_text(encoding='utf-8'))
        if not backend.get('ok'):raise RuntimeError('Backend process check failed')
        report.update(relocated_install=True,runtime=result,backend_control=backend,developer_path_removed=True,unicode_space_path=True,pikachu_host_only=host_only)
    finally:
        uninstaller=target/'unins000.exe'
        if uninstaller.exists():
            run([uninstaller,'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/LOG='+str(validation/'uninstall.log')],env)
            report['uninstalled']=not (target/'runtime/python.exe').exists() and not (target/'PhoneWorkbench8070.exe').exists()
            if (target/'8070-host-policy.json').exists():report['uninstalled']=False
            if report.get('pikachu_host_only'):
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\PhoneWorkbench8070',0,winreg.KEY_READ|winreg.KEY_WOW64_64KEY):
                        report['uninstalled']=False
                except FileNotFoundError:pass
        report['ok']=report['relocated_install'] and report['uninstalled']
        output=ROOT/'releases'/(args.installer.stem+'-'+args.language+'-installation-check.json')
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not report['ok']:raise RuntimeError('Installer validation failed')
    print(json.dumps({'ok':True,'report':str(output)},ensure_ascii=False))

if __name__=='__main__':main()
