"""Build an offline Python-bundled native client and per-user Windows installer."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'iphone_batch/.device-data'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip().removeprefix('v')
BUILD = DATA / 'installer-build' / (VERSION + '-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
STAGE = BUILD / 'app'
RELEASE = ROOT / 'releases'


def run(args):
    print('Running:', subprocess.list2cmdline([str(a) for a in args]), flush=True)
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def ignore_runtime(directory, names):
    ignored = {'__pycache__', 'test', 'tests', 'idlelib', 'ensurepip', 'pip',
               'site-packages', 'direct_url.json'}
    return [n for n in names if n in ignored or n.endswith(('.pyc', '.pyo'))]


def main():
    global STAGE, BUILD
    if len(sys.argv) == 3 and sys.argv[1] == '--repack-stage':
        STAGE = Path(sys.argv[2]).resolve()
        if not STAGE.is_relative_to((DATA / 'installer-build').resolve()):
            raise ValueError('Repack stage must be inside the build cache')
        BUILD = STAGE.parent
        run([sys.executable, ROOT / 'tools/archive_native_vnc_sources.py'])
        shutil.copytree(ROOT / 'native_vnc_source/client', STAGE / 'iphone_batch/.device-data', dirs_exist_ok=True)
        finish()
        return
    STAGE.mkdir(parents=True)
    RELEASE.mkdir(exist_ok=True)
    run([sys.executable, ROOT / 'tools/archive_native_vnc_sources.py'])
    print('Copying isolated Python runtime and dependencies...', flush=True)
    runtime = STAGE / 'runtime'
    runtime.mkdir()
    base = Path(sys.base_prefix)
    for name in ('python.exe', 'pythonw.exe', 'python313.dll', 'python3.dll',
                 'vcruntime140.dll', 'vcruntime140_1.dll', 'LICENSE.txt'):
        shutil.copy2(base / name, runtime / name)
    for name in ('DLLs', 'Lib', 'tcl'):
        shutil.copytree(base / name, runtime / name, ignore=ignore_runtime)
    # A ._pth file prevents registry, PYTHONPATH and an installed Python from
    # providing missing dependencies. Site initializes the pywin32 DLL hooks.
    (runtime / 'python313._pth').write_text('.\nLib\nDLLs\nLib/site-packages\n../iphone_batch\n../iphone_batch/.device-data\nimport site\n', encoding='utf-8')
    shutil.copytree(Path(sys.prefix) / 'Lib/site-packages', runtime / 'Lib/site-packages',
                    ignore=lambda d, ns: [n for n in ns if n == '__pycache__' or n == 'direct_url.json' or n.endswith(('.pyc', '.pyo'))])
    project = STAGE / 'iphone_batch'
    project.mkdir()
    for path in (ROOT / 'iphone_batch').glob('*.py'):
        shutil.copy2(path, project / path.name)
    installed_data = project / '.device-data'
    shutil.copytree(ROOT / 'native_vnc_source/client', installed_data)
    vendor = installed_data / 'upstream-pymobiledevice3-v11.51.0'
    shutil.copytree(ROOT / 'native_vnc_source/upstream', vendor)
    shutil.copytree(ROOT / 'native_vnc_source/viewer/TightVNC', vendor / 'TightVNC')
    for name in ('logs', 'diagnostics', 'workspace'):
        (installed_data / name).mkdir()
    shutil.copy2(ROOT / 'VERSION', STAGE / 'VERSION')
    shutil.copy2(ROOT / 'requirements-windows.lock.txt', STAGE / 'requirements-windows.lock.txt')
    (STAGE / '使用说明.txt').write_text(
        '手机群控 VNC ' + VERSION + '\n\n'
        'Windows 10/11 64 位。自带 Python、后端依赖和 TightVNC Viewer。\n'
        '这是原生客户端，不内嵌 8070 网页。无需预先安装 Python 或 Node。\n\n'
        '首次使用：\n'
        '1. 电脑需已安装 Apple Mobile Device USB 驱动及服务。\n'
        '   缺少时，可安装 Apple 官方 iTunes（含移动设备组件），安装后重启电脑。\n'
        '   有 winget 的电脑也可在终端运行：winget install --id Apple.iTunes --exact\n'
        '2. 解锁手机，USB 连接并确认“信任此电脑”。列表可选中手机并点击“建立所选手机信任”。\n'
        '3. 手机开启开发者模式；首次准备开发者镜像可能需要联网下载。\n'
        '4. 不要同时运行开发版与安装版连接相同手机。\n\n'
        '本安装不导入开发电脑的配对私钥、短信、联系人、API 凭据和设备设置。\n'
        '全局监看默认每秒 1 帧，大屏默认每秒 5 帧。GPU 硬解默认关闭，可手动开启。\n'
        '气泡读取使用界面结构，禁止截图或 OCR 读取。短信发送仍需实际验收。\n'
        '卸载不主动清理用户运行时生成的配对和业务数据。\n', encoding='utf-8-sig')
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
         '--name', 'PhoneWorkbench', '--paths', DATA,
         '--distpath', BUILD / 'frontend', '--workpath', BUILD / 'pyinstaller',
         '--specpath', BUILD, DATA / 'native_vnc_workbench.pyw'])
    shutil.copytree(BUILD / 'frontend/PhoneWorkbench', STAGE, dirs_exist_ok=True)
    finish()


def finish():
    installed_data = STAGE / 'iphone_batch/.device-data'
    runtime = STAGE / 'runtime'
    check = BUILD / 'installation-check.json'
    run([STAGE / 'PhoneWorkbench.exe', '--check-install', check])
    result = json.loads(check.read_text(encoding='utf-8'))
    if not result.get('ok') or Path(result['root']).resolve() != STAGE.resolve():
        raise RuntimeError('Standalone installation check failed: ' + str(result))
    print('Checking isolated source imports without connecting phones...', flush=True)
    run([runtime / 'python.exe', installed_data / 'vnc_av_continuous.py', '--help'])
    compiler = DATA / 'build-tools/InnoSetup/ISCC.exe'
    run([compiler, '/DStageDir=' + str(STAGE), '/DReleaseDir=' + str(RELEASE),
         '/DAppVersion=' + VERSION, ROOT / 'tools/native_vnc_installer.iss'])
    installer = RELEASE / ('PhoneWorkbench-' + VERSION + '-Setup.exe')
    digest = hashlib.file_digest(installer.open('rb'), 'sha256').hexdigest()
    manifest = {'version': VERSION, 'installer': installer.name, 'bytes': installer.stat().st_size,
        'sha256': digest, 'stage': str(STAGE), 'offline_import_check': result,
        'packages': {n: importlib.metadata.version(n) for n in ('av','pymobiledevice3','psutil','pywin32','pyinstaller')},
        'apple_usb_driver_bundled': False, 'phone_function_acceptance': 'pending',
        'signed_installer': False}
    (RELEASE / (installer.stem + '.json')).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (RELEASE / (installer.name + '.sha256')).write_text(digest + '  ' + installer.name + '\n', encoding='ascii')
    print(json.dumps({'installer': str(installer), 'bytes': installer.stat().st_size, 'sha256': digest}), flush=True)


if __name__ == '__main__':
    main()
