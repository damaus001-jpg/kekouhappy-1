"""Build an offline 8070 installer from clean runtime files, never phone data."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'iphone_batch/.device-data/installer-build'
RELEASE=ROOT/'releases'


def command(args,log=None,env=None,timeout=None):
    args=[str(value) for value in args]
    if log:
        with Path(log).open('w',encoding='utf-8') as output:
            result=subprocess.run(args,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=timeout,creationflags=0x08000000)
    else:
        result=subprocess.run(args,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,creationflags=0x08000000)
    if result.returncode:
        detail=Path(log).read_text(encoding='utf-8',errors='replace')[-6000:] if log else result.stderr[-6000:]
        raise RuntimeError('Command failed: '+subprocess.list2cmdline(args)+'\n'+detail)
    return result


def ignore_base(folder,names):
    return [name for name in names if name in ('site-packages','__pycache__','test','tests','idlelib','ensurepip') or name.endswith(('.pyc','.pyo'))]


def ignore_deps(folder,names):
    return [name for name in names if name in ('__pycache__','direct_url.json') or name.endswith(('.pyc','.pyo'))]


def stage_files(stage,build,electron,version,host_only=False):
    print('Copying isolated Python runtime...',flush=True)
    runtime=stage/'runtime';runtime.mkdir(parents=True)
    base=Path(sys.base_prefix)
    for name in ('python.exe','pythonw.exe','python313.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        shutil.copy2(base/name,runtime/name)
    for name in ('DLLs','Lib','tcl'):shutil.copytree(base/name,runtime/name,ignore=ignore_base)
    (runtime/'python313._pth').write_text('.\nLib\nDLLs\nLib/site-packages\n../iphone_batch\n../tools\n..\nimport site\n',encoding='utf-8')
    print('Copying project Python dependencies...',flush=True)
    shutil.copytree(Path(sys.prefix)/'Lib/site-packages',runtime/'Lib/site-packages',ignore=ignore_deps)
    node=shutil.which('node')
    if not node:raise RuntimeError('Node 24+ must be present for packaging')
    if int(command([node,'-p','process.versions.node']).stdout.split('.')[0])<24:raise RuntimeError('Node 24+ required')
    shutil.copy2(node,runtime/'node.exe')
    for name in ('LICENSE','LICENSE.txt'):
        candidate=Path(node).parent/name
        if candidate.is_file():shutil.copy2(candidate,runtime/'NODE-LICENSE.txt');break
    print('Copying 8070 source and web assets; excluding runtime data...',flush=True)
    files=command(['git','-c','safe.directory='+ROOT.as_posix(),'-c','core.quotepath=false','ls-files','iphone_batch']).stdout.splitlines()
    files=sorted(set(files+['iphone_batch/host_access.py','iphone_batch/host_control.py','iphone_batch/web/workspace_theme.js','iphone_batch/message_banner.py']))
    for name in files:
        relative=Path(name)
        if '.device-data' in relative.parts or '__pycache__' in relative.parts or relative.name.startswith('test_'):continue
        if relative.suffix.lower() in ('.db','.sqlite','.log','.pyc'):continue
        destination=stage/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/relative,destination)
    root_files=['VERSION','requirements-windows.lock.txt','README.md','RECOVERY.md']
    if not host_only:root_files+=['Start.ps1','BackendControl.pyw','BackendControl.cmd']
    for name in root_files:
        shutil.copy2(ROOT/name,stage/name)
    (stage/'tools').mkdir(exist_ok=True)
    shutil.copy2(ROOT/'tools/check_8070_install.py',stage/'tools/check_8070_install.py')
    (stage/'使用说明.txt').write_text(
        '皮卡丘手机工作台 '+version+'\n\nWindows 10/11 x64。包含独立桌面入口、Python、Node 和项目依赖，无需预装开发环境。\n'
        '首次使用：\n1. 安装 Apple Mobile Device USB 驱动与服务（可通过 Apple 官方 iTunes 安装）。\n'
        '2. 解锁手机、连接 USB，确认信任电脑并开启开发者模式。首次准备开发者镜像可能需要联网。\n'
        '3. 打开“皮卡丘手机工作台”，点击“启动并打开工作台”，允许 USB 隧道所需的管理员授权。\n'
        '4. 新建短信当前为配置草稿界面，保存草稿不会自动开始任务。\n\n'
        '本安装包不包含开发机的号码、短信、配对、密钥、账号或浏览器登录。\n'
        '新电脑使用自己的本机访问凭据，不需要安装另一个授权客户端。\n'
        '安装结束不会自动启动，也不会连接或操作手机。已有其他手机工作台后台时请先通过对应后台管理关闭。\n'
        '关闭桌面工作台窗口会保留后台；可从菜单“后台管理”彻底关闭本安装目录所属后台。\n'
        '卸载不主动清除运行期间产生的业务数据。\n',encoding='utf-8-sig')
    if host_only:
        (stage/'8070-host-policy.json').write_text('{"protocol":1,"mode":"pikachu-only"}',encoding='utf-8')
        (stage/'使用说明.txt').write_text(
            '皮卡丘手机工作台 '+version+'\n\nWindows 10/11 x64。\n'
            '安装后请通过皮卡丘翻译器的“打新增”图标右键菜单启动或彻底关闭后台，页面使用现有苹果入口。\n'
            '本包没有独立桌面或开始菜单启动入口。安装位置自动登记，无需固定路径。\n'
            'Apple USB驱动需通过Apple官方软件准备；手机需解锁、信任电脑及开启开发者模式。\n'
            '首次开发者镜像准备可能联网，共享USB隧道需要Windows管理员授权。\n'
            '关闭皮卡丘主窗口不等于彻底关闭后台；彻底关闭会断开本后台全部设备连接。\n'
            '安装结束不自动启动，不包含开发机业务数据或密钥。新建短信仍只保存配置草稿。\n'
            '卸载不主动清除运行期间产生的业务数据。\n',encoding='utf-8-sig')
        return
    print('Copying standalone Electron runtime (no other application source or profiles)...',flush=True)
    shutil.copytree(electron,stage/'client',ignore=shutil.ignore_patterns('default_app.asar'))
    (stage/'client/electron.exe').rename(stage/'client/PhoneWorkbench8070Client.exe')
    app=stage/'client/resources/app';shutil.copytree(ROOT/'tools/installer_8070/desktop',app)
    package=json.loads((app/'package.json').read_text());package['version']=version
    (app/'package.json').write_text(json.dumps(package),encoding='utf-8')
    source=(ROOT/'tools/installer_8070/Launcher.cs').read_text(encoding='utf-8').replace('@@VERSION@@',version)
    (build/'Launcher.cs').write_text(source,encoding='utf-8-sig')
    compiler=Path(os.environ.get('SystemRoot','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    command([compiler,'/nologo','/target:winexe','/platform:x64','/codepage:65001','/reference:System.Windows.Forms.dll',
             '/out:'+str(stage/'PhoneWorkbench8070.exe'),build/'Launcher.cs'])


def finish(stage,build,iscc,version):
    environment=os.environ.copy()
    environment.pop('PYTHONPATH',None);environment.pop('PYTHONHOME',None);environment.pop('ELECTRON_RUN_AS_NODE',None)
    environment.update(LOCALAPPDATA=str(build/'isolated-localappdata'),PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
                       PATH=str(stage/'runtime')+os.pathsep+str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'))
    check=build/'offline-install-check.json'
    print('Checking relocated Python imports, bundled Node and hidden signed desktop with zero devices...',flush=True)
    host_only=(stage/'8070-host-policy.json').is_file()
    check_command=([stage/'runtime/python.exe',stage/'tools/check_8070_install.py','--output',check]
                   if host_only else [stage/'PhoneWorkbench8070.exe','--check-install',check])
    command(check_command,env=environment,timeout=150)
    result=json.loads(check.read_text(encoding='utf-8'))
    if not result.get('ok'):raise RuntimeError(str(result))
    # Only a new build stage is cleaned; the development runtime is untouched.
    generated=(stage/'iphone_batch/.device-data').resolve()
    if generated.exists():
        if not generated.is_relative_to(stage.resolve()):raise RuntimeError('Invalid staging cleanup path')
        shutil.rmtree(generated)
    for folder in stage.rglob('__pycache__'):
        target=folder.resolve()
        if not target.is_relative_to(stage.resolve()):raise RuntimeError('Invalid staging cache path')
        shutil.rmtree(target)
    manifest=[]
    for file in sorted(stage.rglob('*')):
        if not file.is_file():continue
        relative=file.relative_to(stage).as_posix()
        if '/.device-data/' in '/'+relative or relative.endswith(('workspace-access.key','.sqlite','.db')):
            raise RuntimeError('Private runtime data in package: '+relative)
        manifest.append({'path':relative,'bytes':file.stat().st_size,'sha256':hashlib.file_digest(file.open('rb'),'sha256').hexdigest()})
    (build/'payload-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Compiling EXE installer; detailed compiler output: '+str(build/'inno.log'),flush=True)
    source=ROOT/'tools/installer_8070/installer.iss'
    defines=['/DHostOnly=1'] if host_only else []
    command([iscc,'/DStageDir='+str(stage),'/DReleaseDir='+str(RELEASE),'/DAppVersion='+version,*defines,source],log=build/'inno.log',timeout=900)
    installer=RELEASE/('皮卡丘手机工作台-'+version+'-安装.exe')
    digest=hashlib.file_digest(installer.open('rb'),'sha256').hexdigest()
    report={'version':version,'project':'8070','installer':installer.name,'bytes':installer.stat().st_size,'sha256':digest,
            'platform':'Windows 10/11 x64','runtime_bundled':True,'standalone_signed_access_client':not host_only,
            'pikachu_host_only':host_only,'control_protocol':1 if host_only else None,
            'apple_usb_driver_bundled':False,'installer_signed':False,'runtime_data_bundled':False,
            'stage':str(stage),'payload_files':len(manifest),'offline_install_check':result,'remote_push':False}
    (RELEASE/(installer.name+'.sha256')).write_text(digest+'  '+installer.name+'\n',encoding='utf-8')
    (RELEASE/(installer.stem+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ok':True,'installer':str(installer),'bytes':report['bytes'],'sha256':digest}),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--electron',type=Path);parser.add_argument('--iscc',type=Path)
    parser.add_argument('--host-only',action='store_true')
    parser.add_argument('--repack-stage',type=Path);parser.add_argument('--crt',type=Path);args=parser.parse_args()
    version=(ROOT/'VERSION').read_text(encoding='utf-8-sig').strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise RuntimeError('Invalid VERSION')
    if sys.version_info[:2]!=(3,13) or Path(sys.prefix)==Path(sys.base_prefix):raise RuntimeError('Run from the project Python 3.13 venv')
    iscc=args.iscc or ROOT/'iphone_batch/.device-data/build-tools/InnoSetup/ISCC.exe'
    if not iscc.is_file():raise RuntimeError('ISCC compiler not found')
    if not args.host_only and (not args.electron or not (args.electron/'electron.exe').is_file()):raise RuntimeError('Electron runtime directory required')
    RELEASE.mkdir(exist_ok=True);CACHE.mkdir(parents=True,exist_ok=True)
    if args.repack_stage:
        stage=args.repack_stage.resolve()
        if not stage.is_relative_to(CACHE.resolve()):raise RuntimeError('Stage must be inside build cache')
        if (stage/'8070-host-policy.json').is_file()!=args.host_only:raise RuntimeError('Repack mode must match existing stage')
        build=stage.parent
    else:
        build=CACHE/('8070-'+version+'-'+datetime.now().strftime('%Y%m%d-%H%M%S'));stage=build/'app'
        stage.mkdir(parents=True)
        print('Build directory: '+str(build),flush=True)
        stage_files(stage,build,args.electron,version,args.host_only)
    crt=args.crt
    if not crt:
        redist=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft Visual Studio/2022/BuildTools/VC/Redist/MSVC'
        candidates=sorted(redist.glob('*/x64/Microsoft.VC143.CRT'))
        if candidates:crt=candidates[-1]
    if not crt or not (crt/'msvcp140_1.dll').is_file():raise RuntimeError('Official x64 VC143 CRT redistributable folder required (--crt)')
    for dll in crt.glob('*.dll'):shutil.copy2(dll,stage/'runtime'/dll.name)
    # Refresh validation and release documentation when reusing a runtime stage.
    for name in ('README.md','RECOVERY.md','VERSION'):shutil.copy2(ROOT/name,stage/name)
    shutil.copy2(ROOT/'tools/check_8070_install.py',stage/'tools/check_8070_install.py')
    shutil.copy2(ROOT/'tools/PACKAGING_8070.md',stage/'tools/PACKAGING_8070.md')
    shutil.copy2(ROOT/'iphone_batch/WORKSPACE.md',stage/'iphone_batch/WORKSPACE.md')
    (ROOT/'.tmp/8070-current-build.json').write_text(json.dumps({'build':str(build),'stage':str(stage)}),encoding='utf-8')
    finish(stage,build,iscc,version)


if __name__=='__main__':main()
