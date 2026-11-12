"""Archive and read original conversations without translation or phone access."""
import json
from pathlib import Path


def archive_reading(source):
    source = Path(source)
    value = json.loads(source.read_text(encoding='utf-8-sig'))
    for message in value.get('messages', []):
        message.pop('translation_zh', None)
    value.pop('translation', None)
    value['translation_enabled'] = False
    output = source.with_name(source.stem+'-reading.json')
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'output': str(output), 'messages': len(value.get('messages', [])),
            'translation_enabled': False, 'api_requests': 0}


def conversations(device, directory=None):
    directory = Path(directory) if directory else Path(__file__).resolve().parent / '.device-data' / 'diagnostics'
    results = []
    paths = [*directory.glob('*-reading.json'), *directory.glob('*-translated.json')]
    for path in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True):
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
                            'baseline_complete': value.get('baseline_complete', False),
                            'incremental': value.get('incremental'),
                            'messages': [{key: m.get(key) for key in (
                                'sequence', 'side', 'time', 'date', 'date_label', 'date_precision',
                                'date_year', 'date_source', 'element_id', 'text', 'kind', 'translation_zh',
                                'message_id', 'guid', 'database_id', 'transport', 'is_read', 'record_source',
                                'has_attachments', 'decode_error')}
                                for m in value.get('messages', [])]})
        except (OSError, ValueError, TypeError):
            continue
    return results
