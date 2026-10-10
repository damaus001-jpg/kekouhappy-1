"""Allow English, URLs, numbers and emoji; never send Chinese text."""
import unicodedata


def validate_send_text(text):
    if not isinstance(text,str) or not 0<len(text.strip())<=6000:
        raise ValueError('发送正文须为 1–6000 字符，可发送英文、链接、数字或 emoji，禁止中文')
    for character in text:
        category = unicodedata.category(character)
        name = unicodedata.name(character, '')
        if name.startswith(('CJK UNIFIED IDEOGRAPH', 'CJK COMPATIBILITY IDEOGRAPH', 'CJK RADICAL', 'KANGXI RADICAL')) or character=='\u3007':
            raise ValueError('检测到中文文字，未发送；请先翻译为英文')
        if category.startswith('C') and character not in '\n\r\t\u200d':
            # Emoji tag sequences are valid components of certain flags.
            if not name.startswith('TAG '):
                raise ValueError('发送正文含不可见控制字符，未发送')
        elif category.startswith('M') and not ('VARIATION SELECTOR' in name or 'COMBINING' in name):
            raise ValueError('发送正文含不支持的文字标记，未发送')
    return text.strip()
