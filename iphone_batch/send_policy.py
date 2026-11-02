"""Validate raw message transport without classifying or translating languages."""


def validate_send_text(text):
    if not isinstance(text,str) or not text.strip() or len(text)>6000:
        raise ValueError('发送正文须为 1–6000 字符')
    if any(ord(character)<32 and character not in '\n\r\t' for character in text):
        raise ValueError('发送正文含无效控制字符，未发送')
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError('发送正文编码无效，未发送') from None
    return text
