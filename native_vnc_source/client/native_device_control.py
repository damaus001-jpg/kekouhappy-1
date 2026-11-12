"""Small shared control policy; defaults to locked on malformed live policy."""
import json
from pathlib import Path

PATH=Path(__file__).resolve().parent/'native-vnc-device-controls.json'


def permission(port):
    if not PATH.exists():return {'enabled':True,'control_enabled':True}
    try:
        data=json.loads(PATH.read_text(encoding='utf-8'))
        return data.get('ports',{}).get(str(port),{'enabled':True,'control_enabled':True})
    except (OSError,ValueError):
        return {'enabled':False,'control_enabled':False}


class ControlPolicy:
    def __init__(self,port):self.port=port
    def __call__(self):
        state=permission(self.port)
        return bool(state.get('enabled') and state.get('control_enabled'))
