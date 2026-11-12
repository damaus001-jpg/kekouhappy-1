"""Parse ordered accessibility observations without treating recycled IDs as keys."""
import calendar
import re

from sms_collect import parse_records

MONTHS={name:i for i,name in enumerate(('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'),1)}
ENGLISH_DATE=re.compile(r'^(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?'
    r'(?P<month>Jan[a-z]*|Feb[a-z]*|Mar[a-z]*|Apr[a-z]*|May|Jun[a-z]*|Jul[a-z]*|Aug[a-z]*|Sep[a-z]*|Oct[a-z]*|Nov[a-z]*|Dec[a-z]*)'
    r'\s+(?P<day>\d{1,2})(?:,?\s+(?P<year>\d{4}))?(?:\s+at\s+\d{1,2}:\d{2}(?:\s*[AP]M)?)?$',re.I)
CHINESE_DATE=re.compile(r'^(?:(?P<year>\d{4})年)?(?P<month>\d{1,2})月(?P<day>\d{1,2})[日号](?:\s+.*)?$')
ISO_DATE=re.compile(r'^(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})(?:\s+.*)?$')
RELATIVE_DATE=re.compile(r'^(Today|Yesterday|今天|昨天|前天|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*)(?:\s+(?:at\s+)?\d{1,2}:\d{2}(?:\s*[AP]M)?)?$',re.I)


def date_separator(caption):
    text=caption.strip()
    match=ENGLISH_DATE.fullmatch(text)
    if match:
        month=MONTHS[match['month'][:3].lower()]
    else:
        match=CHINESE_DATE.fullmatch(text) or ISO_DATE.fullmatch(text)
        month=int(match['month']) if match else None
    if match:
        day=int(match['day'])
        year=int(match['year']) if match['year'] else None
        if not 1<=month<=12 or not 1<=day<=calendar.monthrange(year or 2000,month)[1]:
            return None
        return {'date':f'{year:04d}-{month:02d}-{day:02d}' if year else f'{month:02d}-{day:02d}',
                'date_label':text,'date_precision':'day' if year else 'month-day',
                'date_source':'ui_separator','date_year':year}
    if RELATIVE_DATE.fullmatch(text):
        return {'date':None,'date_label':text,'date_precision':'relative-label',
                'date_source':'ui_separator','date_year':None}
    return None


def parse_bubble_records(records, contact):
    header={'caption':contact+', Show Conversation Details, Button'}
    messages=[]
    unclassified=[]
    current_date=None
    for record in records:
        caption=record.get('caption') or ''
        # Parse this occurrence itself. A node ID can belong to a different
        # message later in the traversal; never look its body up in an ID map.
        _,parsed,unknown=parse_records([header,record])
        if parsed:
            message=dict(parsed[0])
        elif 'Includes picture' in caption:
            side=('outgoing' if caption.startswith(('Your iMessage,','Your Message,','Your SMS,','Your Text Message,'))
                  else 'incoming' if caption.startswith(contact+', ') else 'unknown')
            message={'side':side,'time':None,'kind':'attachment','text':'[图片：未读取图片内容]',
                     'element_id':record.get('platform_identifier'),'raw_caption':caption}
        else:
            separator=date_separator(caption)
            if separator is not None:
                current_date=separator
            unclassified.extend(unknown)
            continue
        message.update(current_date or {'date':None,'date_label':None,'date_precision':'unknown',
                                        'date_source':None,'date_year':None})
        message['sequence']=len(messages)+1
        messages.append(message)
    return messages,unclassified
