"""Read saved translated conversations without touching a phone."""
import json
from pathlib import Path


def conversations(device, directory=None):
    directory = Path(directory) if directory else Path(__file__).resolve().parent / '.device-data' / 'diagnostics'
    results = []
    for path in sorted(directory.glob('*-translated.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            if value.get('device') != device or not value.get('contact'):
                continue
            results.append({'id': path.stem, 'contact': value['contact'], 'created': value.get('created'),
                            'source': value.get('source', 'saved'), 'phone_number': value.get('phone_number'),
                            'context_fingerprint': value.get('context_fingerprint'),
                            'native_context': value.get('native_context'),
                            'scope': value.get('scope'),
                            'history_complete': value.get('history_complete', False),
                            'messages': [{key: m.get(key) for key in (
                                'sequence', 'side', 'time', 'text', 'kind', 'translation_zh',
                                'message_id', 'guid', 'database_id', 'transport', 'is_read', 'record_source')}
                                for m in value.get('messages', [])]})
        except (OSError, ValueError, TypeError):
            continue
    return results
