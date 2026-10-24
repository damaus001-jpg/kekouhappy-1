"""User-confirmed contact facts, isolated by device and normalized phone number."""
from datetime import datetime, timezone
import hashlib
import json

from native_conversation import phone_key

FIELDS = ('姓名', '年龄', '工作', '地区', '婚否', '兴趣爱好', '其他信息', '资料依据', '待确认')


def profile_path(root, device, conversation):
    number = phone_key(str(conversation.get('phone_number') or conversation.get('contact') or ''))
    # An unknown number cannot safely merge records solely by a display name.
    identity = number or 'conversation:' + conversation['id']
    key = hashlib.sha256(json.dumps([device, identity], ensure_ascii=False).encode()).hexdigest()
    return root / 'workspace' / 'contact-profiles' / (key + '.json')


def validate_fields(fields):
    if not isinstance(fields, dict) or set(fields) - set(FIELDS):
        raise ValueError('联系人资料字段无效')
    result = {}
    for key in FIELDS:
        value = fields.get(key, '')
        if not isinstance(value, str) or len(value) > (8000 if key in FIELDS[6:] else 1000):
            raise ValueError('联系人资料内容过长或格式无效')
        result[key] = value.strip()
    return result


def read_profile(root, device, conversation):
    path = profile_path(root, device, conversation)
    if not path.exists():
        return {'fields': {}, 'updated': None}
    value = json.loads(path.read_text(encoding='utf-8'))
    return {'fields': validate_fields(value['fields']), 'updated': value['updated']}


def save_profile(root, device, conversation, fields):
    value = {'fields': validate_fields(fields), 'updated': datetime.now(timezone.utc).isoformat()}
    path = profile_path(root, device, conversation)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
    return value
