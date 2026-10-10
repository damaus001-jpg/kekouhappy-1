"""Local OCR fallback: identify a unique phone + age before a notification tap."""
import asyncio
import base64
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import uuid


def age(value):
    value = value.lower().strip()
    if value in ('now','刚刚'):
        return 0
    match = re.fullmatch(r'(\d+)\s*(?:minutes?|mins?|m)\s*ago',value)
    return int(match[1]) if match else None


def locate(lines, expected, width, height):
    minutes = age(expected['time'])
    if minutes is None:
        raise ValueError('通知时间格式尚未支持触控定位，请重新检查通知')
    digits = re.sub(r'\D','',expected['phone_number'])
    candidates = []
    for line in lines:
        if '+' not in line['text'] or digits not in re.sub(r'\D','',line['text']):
            continue
        words = line['words']
        if not words:
            continue
        y = min(w['y'] for w in words)
        bottom = max(w['y']+w['h'] for w in words)
        same_age = [r for r in lines if age(r['text'])==minutes and r['words']
                    and abs(min(w['y'] for w in r['words'])-y)<height*.025]
        preview=re.sub(r'\W','',expected.get('preview','')).casefold()
        same_preview=[r for r in lines if r['words'] and len(preview)>=4
            and preview in re.sub(r'\W','',r['text']).casefold()
            and 0<min(w['y'] for w in r['words'])-bottom<height*.06]
        if len(same_age)==1 or len(same_preview)==1:
            candidates.append({'x':.5,'y':(y+bottom)/2/height+.01})
    if len(candidates)!=1 or not .15<candidates[0]['y']<.90:
        raise ValueError('通知画面中的号码和时间无法唯一定位，未点击')
    return candidates[0]


def locate_open(lines,expected,width,height):
    anchor=locate(lines,expected,width,height)
    buttons=[word for line in lines for word in line['words']
        if word['text'].strip().casefold() in ('open','打开')
        and abs((word['y']+word['h']/2)/height-anchor['y'])<.055]
    if not buttons:return None
    if len(buttons)!=1:raise ValueError('通知的 Open 按钮不唯一，未点击')
    word=buttons[0]
    return {'x':(word['x']+word['w']/2)/width,'y':(word['y']+word['h']/2)/height}


def frame(phone, output):
    import av
    info=phone.request(phone.base,'/codec')
    decoder=av.CodecContext.create('hevc','r')
    decoder.extradata=base64.b64decode(info['description'])
    def exact(response, size):
        data=bytearray()
        while len(data)<size:
            part=response.read(size-len(data))
            if not part:raise ValueError('投屏连接中断，未点击通知')
            data.extend(part)
        return bytes(data)
    with phone.opener.open(phone.base+'/stream.bin',timeout=10) as response:
        for _ in range(120):
            length=struct.unpack('>I',exact(response,4))[0]
            if not 1<length<20000000:raise ValueError('无效投屏帧')
            frames=decoder.decode(av.Packet(exact(response,length)[1:]))
            if frames:
                image=frames[-1].to_image()
                if image.width>=image.height:raise ValueError('通知触控定位仅支持竖屏')
                image.save(output)
                return image.width,image.height
    raise ValueError('未获取通知画面，未点击')


async def tap_notification(service,phone,device,expected):
    if sys.platform!='win32':raise ValueError('原生通知激活未生效，当前系统没有本地定位兜底')
    from native_workspace import ROOT
    from message_notifications import elements,parse_notification
    from fixed_coordinates import tap
    output=ROOT/'diagnostics'/('notification-click-'+uuid.uuid4().hex+'.png')
    output.parent.mkdir(parents=True,exist_ok=True)
    try:
        width,height=await asyncio.to_thread(frame,phone,output)
        process=await asyncio.to_thread(subprocess.run,
            ['powershell','-NoProfile','-File',str(Path(__file__).with_name('notification_ocr.ps1')),
             '-ImagePath',str(output)],capture_output=True,timeout=25,encoding='utf-8',creationflags=0x08000000)
        if process.returncode:raise ValueError('本地通知定位失败，未点击')
        lines=json.loads(process.stdout)['lines']
        try:point=locate_open(lines,expected,width,height) or locate(lines,expected,width,height)
        except ValueError:
            (ROOT/'diagnostics'/'notification-location-error.json').write_text(
                json.dumps({'width':width,'height':height,'expected':expected,'lines':lines},ensure_ascii=False),encoding='utf-8')
            raise
        # OCR is only for geometry. Source and recipient still come from a
        # fresh native Messages notification, never from OCR alone.
        fresh=await elements(service)
        matches=[row for item in fresh if (row:=parse_notification(item.caption,item.platform_identifier,device))
                 and row['id']==expected['id'] and row['phone_number']==expected['phone_number']
                 and row['preview']==expected['preview'] and row['grouped']==expected['grouped']]
        if len(matches)!=1:raise ValueError('定位期间通知发生变化，未点击')
        await tap(phone,point)
    finally:
        output.unlink(missing_ok=True)
