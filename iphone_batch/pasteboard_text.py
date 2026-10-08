"""Extract plain text from UIKit attributed-string clipboard archives."""
import plistlib

ATTRIBUTED_UTI = 'com.apple.uikit.attributedstring'
MAX_ARCHIVE_BYTES = 1024 * 1024


def archive_text(raw):
    if not isinstance(raw, (bytes, bytearray)) or not 0 < len(raw) <= MAX_ARCHIVE_BYTES:
        return None
    try:
        archive = plistlib.loads(raw)
    except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException):
        return None
    if not isinstance(archive, dict):
        return None
    objects = archive.get('$objects', [])
    if not isinstance(objects, list):
        return None

    def resolve(value, visited=(), depth=0):
        if depth > 20:
            return None
        if isinstance(value, plistlib.UID):
            index = value.data
            if index <= 0 or index >= len(objects) or index in visited:
                return None
            return resolve(objects[index], (*visited, index), depth + 1)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # Never concatenate arbitrary archive strings: font names, URLs and
            # other attribute values are not part of the copied message body.
            for key in ('NSString', 'NS.string', 'string'):
                if key in value:
                    result = resolve(value[key], visited, depth + 1)
                    if result is not None:
                        return result
        return None

    top = archive.get('$top')
    if isinstance(top, dict):
        return resolve(top.get('root', top.get('NSKeyedArchiveRootObjectKey')))
    return resolve(archive)


def attributed_text(snapshot):
    board = snapshot.get('pasteboard', snapshot)
    if not isinstance(board, dict):
        return None
    for item in board.get('items', []) or []:
        if not isinstance(item, dict):
            continue
        datum = (item.get('data') or {}).get(ATTRIBUTED_UTI)
        if isinstance(datum, dict):
            value = archive_text(datum.get('data'))
            if value is not None:
                return value
    return None


def install():
    from pymobiledevice3.remote.core_device import pasteboard_service
    if getattr(pasteboard_service.snapshot_text, '_supports_attributed', False):
        return
    original = pasteboard_service.snapshot_text
    def snapshot_text(snapshot):
        value = original(snapshot)
        return value if value is not None else attributed_text(snapshot)
    snapshot_text._supports_attributed = True
    pasteboard_service.snapshot_text = snapshot_text
