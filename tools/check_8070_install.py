"""Offline relocated-runtime and signed desktop check; never discovers phones."""
import argparse
import ctypes
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request


def check_host_backend(output, version):
    """Serve a hidden zero-device fixture; no shared tunnel or USB discovery."""
    import socket
    from host_access import make_proof
    from workspace_access import signed_opener
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port=listener.getsockname()[1]
    folder=output.parent/'isolated-host-dashboard';folder.mkdir(parents=True,exist_ok=True)
    process=subprocess.Popen([str(ROOT/'runtime/python.exe'),'-c',
        'import controller; controller.discover=lambda:[]; import dashboard; dashboard.main()',
        '--port',str(port),'--device-map',str(folder/'devices.json')],cwd=ROOT/'iphone_batch',
        stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=0x08000000)
    try:
        process.stdin.write((json.dumps(make_proof('serve',ROOT))+'\n').encode('utf-8'));process.stdin.close()
        base=f'http://127.0.0.1:{port}';opener=signed_opener();ready=False
        for _ in range(150):
            if process.poll() is not None:raise RuntimeError('Zero-device dashboard exited: '+process.stderr.read().decode('utf-8',errors='replace')[-1500:])
            try:
                with opener.open(base+'/',timeout=1) as response:
                    page=response.read().decode('utf-8');ready=response.status==200
                if ready:break
            except OSError:time.sleep(.15)
        if not ready:raise RuntimeError('Zero-device host dashboard did not start')
        unsigned=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with unsigned.open(base+'/',timeout=2):raise RuntimeError('Unsigned workspace request accepted')
        except urllib.error.HTTPError as error:
            if error.code!=403:raise
        with opener.open(base+'/api/state',timeout=5) as response:data=json.load(response)
        if data['devices'] or 'id="new-sms-task"' not in page or 'v'+version not in page:
            raise RuntimeError('Zero-device host workspace content mismatch')
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=10)
        process.stderr.close()
    environment=os.environ.copy()
    cli=[str(ROOT/'runtime/python.exe'),str(ROOT/'iphone_batch/host_control.py')]
    proof=make_proof('status',ROOT)
    authorized=subprocess.run(cli+['status'],input=json.dumps(proof)+'\n',capture_output=True,text=True,
                              encoding='utf-8',env=environment,timeout=20,creationflags=0x08000000)
    state=json.loads(authorized.stdout)
    if authorized.returncode or not state.get('ok') or state.get('state')!='stopped':
        raise RuntimeError('Installed host status failed: '+authorized.stdout+authorized.stderr)
    for action in ('start','stop'):
        denied=subprocess.run(cli+[action],input='',capture_output=True,text=True,encoding='utf-8',
                              timeout=20,creationflags=0x08000000)
        if denied.returncode!=3 or json.loads(denied.stdout).get('code')!='AUTH_REQUIRED':
            raise RuntimeError('Unsigned host control was not denied')
    direct=subprocess.run([str(ROOT/'runtime/python.exe'),str(ROOT/'iphone_batch/dashboard.py')],
        input='',capture_output=True,text=True,encoding='utf-8',timeout=30,creationflags=0x08000000)
    if direct.returncode==0 or '请通过皮卡丘操作8070后台' not in direct.stderr:
        raise RuntimeError('Direct installed dashboard launch was not denied')
    return {'ok':True,'unsigned_status':403,'signed_status':200,'version':'v'+version,
            'new_sms_entry':True,'devices':0,'phone_connections_tested':False,
            'client':'pikachu-host','signed_control_status':state['state'],
            'unsigned_start_stop_denied':True,'direct_dashboard_denied':True}

ROOT=Path(__file__).resolve().parents[1]


def check(output):
    modules={}
    for name in ('tkinter','av','cv2','numpy','psutil','win32api','win32clipboard',
                 'cryptography','PIL','onnxruntime','rapidocr','pymobiledevice3',
                 'dashboard','backend_control','viewer_patch','native_workspace','native_message_page'):
        module=importlib.import_module(name)
        filename=getattr(module,'__file__',None)
        if filename and not Path(filename).resolve().is_relative_to(ROOT):
            raise RuntimeError('Import escaped installed root: '+name+' '+filename)
        modules[name]={'ok':True,'path':filename}
    import tkinter
    tcl=tkinter.Tcl();tcl_library=tcl.eval('info library')
    if not Path(tcl_library).resolve().is_relative_to(ROOT):raise RuntimeError('Tcl escaped installed root')
    mismatches=[]
    for line in (ROOT/'requirements-windows.lock.txt').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'):continue
        name,expected=line.split('==')
        try:actual=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:actual=None
        if actual!=expected:mismatches.append({'name':name,'expected':expected,'actual':actual})
    if mismatches:raise RuntimeError('Installed requirements mismatch: '+json.dumps(mismatches))
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];kernel.GetModuleHandleW.restype=ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_ulong]
    crt={}
    for dll in ('vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll','msvcp140_1.dll'):
        handle=kernel.GetModuleHandleW(dll)
        buffer=ctypes.create_unicode_buffer(32768)
        if not handle or not kernel.GetModuleFileNameW(handle,buffer,len(buffer)):raise RuntimeError('CRT module not loaded: '+dll)
        if not Path(buffer.value).resolve().is_relative_to(ROOT):raise RuntimeError('CRT escaped installed root: '+buffer.value)
        crt[dll]=buffer.value
    if sys.flags.isolated!=1:raise RuntimeError('Python runtime is not isolated')
    node=ROOT/'runtime/node.exe'
    node_result=subprocess.run([str(node),'-p','process.versions.node'],capture_output=True,text=True,check=True,timeout=10)
    if int(node_result.stdout.split('.')[0])<24:raise RuntimeError('Node 24+ required')
    version=(ROOT/'VERSION').read_text(encoding='utf-8-sig').strip()
    if (ROOT/'8070-host-policy.json').is_file():
        result=check_host_backend(output,version)
        return {'ok':True,'version':version,'root':str(ROOT),'python':sys.version,'executable':sys.executable,
                'isolated':True,'imports':modules,'tcl_library':tcl_library,'node_version':node_result.stdout.strip(),
                'desktop':result,'crt':crt,'phone_ui_started':False,'phone_connections_tested':False}
    desktop_output=output.with_suffix('.desktop.json')
    environment=os.environ.copy();environment.pop('ELECTRON_RUN_AS_NODE',None)
    environment['PATH']=str(ROOT/'runtime')+os.pathsep+str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')
    environment.pop('PYTHONHOME',None);environment.pop('PYTHONPATH',None)
    desktop=subprocess.run([str(ROOT/'client/PhoneWorkbench8070Client.exe'),'--check-desktop',str(desktop_output)],
                           cwd=ROOT,env=environment,capture_output=True,text=True,encoding='utf-8',errors='replace',
                           timeout=80,creationflags=0x08000000)
    if not desktop_output.is_file():raise RuntimeError('Desktop check produced no report: '+desktop.stderr[-1500:])
    result=json.loads(desktop_output.read_text(encoding='utf-8'))
    if not result.get('ok'):raise RuntimeError('Desktop check failed: '+str(result))
    if result.get('version')!='v'+version:raise RuntimeError('Desktop UI version does not match installed VERSION')
    return {'ok':True,'version':version,'root':str(ROOT),'python':sys.version,'executable':sys.executable,
            'isolated':True,'imports':modules,'tcl_library':tcl_library,'node_version':node_result.stdout.strip(),
            'desktop':result,'crt':crt,'phone_ui_started':False,'phone_connections_tested':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    try:
        report=check(args.output)
    except Exception as error:
        import traceback
        report={'ok':False,'error':str(error),'traceback':traceback.format_exc()}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.exit(0 if report['ok'] else 1)
