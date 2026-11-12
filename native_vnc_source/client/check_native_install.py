"""Offline installation check. Does not enumerate, pair or control phones."""
import importlib
import json
from pathlib import Path
import sys

data = Path(__file__).resolve().parent
root = data.parents[1]
sys.path.insert(0, str(data.parent))
sys.path.insert(0, str(data))
checks = {}
for name in ('tkinter', 'av', 'cv2', 'numpy', 'psutil', 'win32job',
             'cryptography', 'pymobiledevice3', 'native_vnc_worker',
             'native_reverse_reader', 'native_decode_accel', 'pairing_patch',
             'message_archive', 'workspace_service', 'message_backup'):
    try:
        module = importlib.import_module(name)
        location = Path(module.__file__).resolve()
        if not location.is_relative_to(root):
            raise RuntimeError('Dependency outside installation: ' + str(location))
        checks[name] = {'ok': True, 'path': str(location)}
    except Exception as exc:
        checks[name] = {'ok': False, 'error': repr(exc)}
for relative in ('VERSION', 'PhoneWorkbench.exe', 'runtime/python.exe',
                 'iphone_batch/.device-data/upstream-pymobiledevice3-v11.51.0/pymobiledevice3/remote/core_device/vnc_server.py',
                 'iphone_batch/.device-data/upstream-pymobiledevice3-v11.51.0/TightVNC/PFiles/TightVNC/tvnviewer.exe'):
    checks[relative] = {'ok': (root / relative).is_file()}
ok = all(value['ok'] for value in checks.values())
try:
    import tkinter
    checks['Tcl runtime'] = {'ok': True, 'version': tkinter.Tcl().eval('info patchlevel')}
except Exception as exc:
    checks['Tcl runtime'] = {'ok': False, 'error': repr(exc)}
ok = all(value['ok'] for value in checks.values())
print(json.dumps({'ok': ok, 'root': str(root), 'executable': sys.executable, 'checks': checks}, indent=2))
sys.exit(0 if ok else 1)
