"""Slow reverse accessibility traversal. Pictures never terminate the read."""
from native_conversation import phone_key
from native_ui_scan import scan
from sms_collect import parse_records
from native_bubble_records import parse_bubble_records

MARKER=', Show Conversation Details, Button'


def recipient_number(caption):
    # Never treat a number inside an SMS body as the conversation identity.
    if MARKER not in (caption or ''):
        return None
    return phone_key(caption.split(MARKER,1)[0])


async def capture_reverse(service):
    scanned=await scan(service,limit=3000,seconds=115,settle=.20,
        start_from_last=True,reverse=True,
        stop_when=lambda item:bool(recipient_number(item.caption or '')))
    if scanned.reason!='target_found':
        raise ValueError(f'倒序读取尚未完成：未读到会话顶部的完整手机号（{scanned.reason}，已遍历 {len(scanned)} 个元素）；遇到图片不会停止')
    records=[{'caption':item.caption or '', 'platform_identifier':item.platform_identifier}
             for item in reversed(scanned)]
    numbers={recipient_number(r['caption']) for r in records if recipient_number(r['caption'])}
    if len(numbers)!=1:
        raise ValueError('未唯一确认会话手机号，未保存为可发送会话')
    number=numbers.pop()
    contact,_,_=parse_records(records)
    ordered,unknown=parse_bubble_records(records,contact or number)
    if not ordered:
        raise ValueError('已读到手机号，但本轮没有读到可保存的气泡')
    for index,message in enumerate(ordered,1):
        message['sequence']=index
    return {'contact':contact or number,'phone_number':number,'messages':ordered,
        'raw_elements':records,'unclassified':unknown,'source':'native-reverse-until-number',
        'read_direction':'bottom-to-top','stop_reason':'phone_number_found',
        'parser_version':2,
        'element_interval_seconds':.20,'elapsed_seconds':scanned.elapsed,
        'history_complete':False,'ui_history_complete':False,
        'scope':f'已从下向上慢速遍历至会话手机号，共 {len(ordered)} 条；图片保留为附件占位，数据库历史完整性未核对'}
