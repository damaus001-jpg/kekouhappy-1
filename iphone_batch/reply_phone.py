"""USB reply actions through the existing local viewer. No translation required."""
import base64
from difflib import SequenceMatcher
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import threading
import time
import urllib.request
from controller import command_for, device_environment
from reply_assistant import fingerprint

ROOT = Path(__file__).resolve().parent / '.device-data'


def normalized(value):
    return re.sub(r'\W+', '', value).casefold()


class PhoneDriver:
    def __init__(self, manager='http://127.0.0.1:8070'):
        raise RuntimeError('用户要求禁止截屏定位；此视觉驱动已禁用，请使用系统界面元素驱动')
        self.manager = manager; self.device = None; self.port = None; self.ocr = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.lock = threading.RLock()

    def request(self, path, body=None, manager=False):
        base = self.manager if manager else 'http://127.0.0.1:' + str(self.port)
        req = urllib.request.Request(base+path, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json'}, method='GET' if body is None else 'POST')
        with self.opener.open(req, timeout=30) as response:
            raw = response.read(1024*1024)
        try:
            return json.loads(raw)
        except ValueError:
            return {'ok':raw.strip()==b'ok'}

    def select(self, device):
        state = self.request('/api/state', manager=True)
        rows = [row for row in state['devices'] if row['udid']==device and row['ready']]
        if not rows:
            raise ValueError('手机投屏未就绪')
        self.device = device; self.port = rows[0]['port']
        self.request('/api/select', {'udid':device}, manager=True)

    def frame(self):
        import av
        info = self.request('/codec')
        codec = av.CodecContext.create('hevc', 'r'); codec.extradata = base64.b64decode(info['description'])
        started = time.monotonic(); latest = None
        def exact(stream, count):
            data = bytearray()
            while len(data)<count:
                chunk = stream.read(count-len(data))
                if not chunk:
                    raise EOFError('视频流中断')
                data.extend(chunk)
            return bytes(data)
        with self.opener.open('http://127.0.0.1:'+str(self.port)+'/stream.bin', timeout=12) as stream:
            while time.monotonic()-started<12:
                length = struct.unpack('>I', exact(stream,4))[0]
                if not 1<=length<=20000000:
                    raise ValueError('视频帧长度无效')
                data = exact(stream,length)
                frames = codec.decode(av.Packet(data[1:]))
                if frames:
                    latest = frames[-1].to_image()
                    if time.monotonic()-started>=2:
                        return latest
        raise TimeoutError('未获得当前视频画面')

    def lines(self, image):
        import numpy as np
        if self.ocr is None:
            from rapidocr import RapidOCR
            self.ocr = RapidOCR(params={'Global.model_root_dir':str(ROOT/'ocr-models')})
        result = self.ocr(np.asarray(image))
        if result.boxes is None:
            return []
        output=[]
        for box,text,score in zip(result.boxes,result.txts,result.scores):
            if float(score)<0.65:
                continue
            xs=[float(p[0]) for p in box];ys=[float(p[1]) for p in box]
            output.append({'text':text,'x':min(xs),'y':min(ys),'w':max(xs)-min(xs),'h':max(ys)-min(ys),'score':float(score)})
        return sorted(output,key=lambda row:(row['y'],row['x']))

    def tap(self, x, y):
        coords={'x':round(x*65535),'y':round(y*65535)}
        try:
            self.request('/touch',{'type':'contact',**coords});time.sleep(0.08)
        finally:
            self.request('/touch',{'type':'release',**coords})
        time.sleep(0.5)

    def swipe(self, down=False):
        start,end=(.35,.75) if down else (.75,.35)
        try:
            for i in range(13):
                self.request('/touch',{'type':'contact','x':32768,'y':round((start+(end-start)*i/12)*65535)})
                time.sleep(.025)
        finally:
            self.request('/touch',{'type':'release','x':32768,'y':round(end*65535)})
        time.sleep(.6)

    def unread_rows(self, image, lines):
        import cv2
        import numpy as np
        pixels=np.asarray(image).astype('int16');r,g,b=pixels[:,:,0],pixels[:,:,1],pixels[:,:,2]
        height,width=pixels.shape[:2]
        mask=((b>150)&(b-r>80)&(g>60)&(g<210)&(b-g>25)).astype('uint8')
        mask[:int(height*.14)]=0;mask[int(height*.9):]=0;mask[:,int(width*.065):]=0
        count,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
        rows=[]
        for i in range(1,count):
            x,y,w,h,area=stats[i]
            if area<25 or not .004*width<w<.06*width or not .5<w/h<2:
                continue
            cy=centers[i][1]
            candidates=[line for line in lines if width*.16<line['x']<width*.55 and cy-height*.045<line['y']<cy+height*.015]
            if not candidates:
                continue
            title=min(candidates,key=lambda line:(line['y']//(height*.025),line['x']))
            if title['y']<height*.12:
                continue
            preview=' '.join(line['text'] for line in lines if line['x']>width*.15 and title['y']+title['h']<line['y']<cy+height*.055)
            rows.append({'name':title['text'],'preview':preview,'x':.5,'y':float(cy/height)})
        return sorted(rows,key=lambda row:row['y'])

    def find_unread(self, stop=None):
        # Only operate inside the owner's chosen Unread filter.
        previous=None
        for page in range(30):
            if stop and stop.is_set():
                return None
            image=self.frame();lines=self.lines(image)
            if not any(normalized(line['text']) in ('unread','未读','未讀') and line['y']<image.height*.15 for line in lines):
                raise ValueError('请先在手机打开“未读”筛选列表')
            rows=self.unread_rows(image,lines)
            if rows:
                return rows[0]
            signature=tuple(normalized(line['text']) for line in lines if image.height*.16<line['y']<image.height*.85)
            if signature==previous:
                # Return to the top before the next polling pass.
                for _ in range(min(page+1,30)):
                    self.swipe(down=True)
                return None
            previous=signature;self.swipe()
        raise ValueError('扫描达到 30 屏上限，未确认列表底部，请人工检查')

    def open(self, candidate):
        # Re-check current row before tapping; OCR list text is a target hint, not a database ID.
        image=self.frame();rows=self.unread_rows(image,self.lines(image))
        match=[row for row in rows if row['name']==candidate['name'] and row['preview']==candidate['preview']]
        if len(match)!=1:
            raise ValueError('未读行已变化或身份不唯一，暂停打开')
        self.tap(match[0]['x'],match[0]['y'])

    def native_items(self):
        result=subprocess.run(command_for(self.device,['developer','accessibility','list-items']),
            env=device_environment(self.device),capture_output=True,text=True,encoding='utf-8',timeout=25)
        if result.returncode:
            raise ValueError('系统界面文字读取失败')
        return json.loads(result.stdout)

    def read_context(self):
        # The screenshot bounds the context to one screen. Native captions refine matching OCR bubbles.
        image=self.frame();lines=self.lines(image)
        items=self.native_items();contact=None
        for item in items:
            text=item.get('caption') or ''
            if ', Show Conversation Details, Button' in text:
                contact=text.split(', Show Conversation Details, Button')[0];break
        if not contact:
            raise ValueError('当前页面不是短信对话，未确认联系人')
        native=[]
        from sms_collect import TIME
        for item in items:
            caption=item.get('caption') or ''
            match=TIME.search(caption);text=caption[:match.start()] if match else caption
            side=None
            for prefix in ('Your iMessage, ','Your Message, ','Your SMS, '):
                if text.startswith(prefix):
                    side='outgoing';text=text[len(prefix):];break
            if text.startswith(contact+', '):
                side='incoming';text=text[len(contact)+2:]
            if side and text!='Includes picture':
                native.append({'side':side,'text':text,'time':match[1] if match else None})
        import numpy as np
        from text_translation import group_lines
        filtered=[{'source':l['text'],'x':l['x'],'y':l['y'],'w':l['w'],'h':l['h']} for l in lines if image.height*.15<l['y']<image.height*.84 and re.search(r'[A-Za-z]{2}',l['text'])]
        groups=group_lines(filtered,image.width,image.height,np.asarray(image))
        messages=[]
        for group in sorted(groups,key=lambda row:row['y']):
            best=max(native,key=lambda m:SequenceMatcher(None,normalized(m['text']),normalized(group['source'])).ratio(),default=None)
            if best and SequenceMatcher(None,normalized(best['text']),normalized(group['source'])).ratio()>=.80:
                messages.append(best)
            else:
                # Do not guess sender identity from unclassified or clipped OCR text.
                raise ValueError('当前屏幕有文字未能与系统短信描述匹配，请调整页面后重读')
        if not messages:
            raise ValueError('当前屏幕没有完整可识别的文字气泡')
        ROOT.joinpath('diagnostics').mkdir(parents=True,exist_ok=True)
        image.save(ROOT/'diagnostics'/'reply-context-current.png')
        return {'contact':contact,'messages':messages,'source':'one-screen-native-text-with-local-position-matching'}

    def verify_target(self,candidate,context):
        name=normalized(candidate['name'].split('…')[0].split('...')[0])
        if len(name)<5 or not normalized(context['contact']).startswith(name[:12]):
            raise ValueError('打开后的联系人与目标行不匹配')

    def back_to_unread(self):
        # Back navigation only after native conversation header confirmation.
        items=self.native_items()
        if any(', Show Conversation Details, Button' in (item.get('caption') or '') for item in items):
            self.tap(.10,.078)
        image=self.frame();lines=self.lines(image)
        if not any(normalized(line['text']) in ('unread','未读','未讀') and line['y']<image.height*.15 for line in lines):
            raise ValueError('未返回未读列表，请手动选择未读筛选')

    def keys(self,usages):
        try:
            self.request('/key',{'usages':usages});time.sleep(.15)
        finally:
            self.request('/key',{'usages':[]})
        time.sleep(.3)

    def send_text(self,text,contact,expected_fingerprint):
        current=self.read_context()
        if current['contact']!=contact or fingerprint(current['messages'])!=expected_fingerprint:
            raise ValueError('消息上下文发生变化，未发送')
        image=self.frame();lines=self.lines(image)
        fields=[l for l in lines if normalized(l['text']) in ('imessage','textmessage','message','短信','信息') and l['y']>image.height*.40 and l['x']>image.width*.15]
        if len(fields)!=1:
            raise ValueError('输入框不为空或未定位，未粘贴')
        field=fields[0]
        self.tap((field['x']+field['w']/2)/image.width,(field['y']+field['h']/2)/image.height)
        self.paste_text(text)
        image=self.frame()
        # Find the circular blue/green send control at the right side above the keyboard.
        import cv2
        import numpy as np
        pixels=np.asarray(image).astype('int16');r,g,b=pixels[:,:,0],pixels[:,:,1],pixels[:,:,2]
        mask=(((b-r>70)&(b>150)&(g>60))|((g-r>60)&(g>b+25)&(g>140))).astype('uint8')
        mask[:int(image.height*.35)]=0;mask[int(image.height*.95):]=0;mask[:,:int(image.width*.02)]=0
        count,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
        circles=[]
        for i in range(1,count):
            x,y,w,h,area=stats[i]
            if x>image.width*.80 and .035*image.width<w<.10*image.width and .75<w/h<1.3 and area>w*h*.45:
                circles.append((float(centers[i][0]/image.width),float(centers[i][1]/image.height)))
        if len(circles)!=1:
            raise ValueError('发送按钮位置不唯一，文本已粘贴但未点击发送')
        # Native input description must contain the exact payload before the irreversible tap.
        items=self.native_items()
        for _ in range(2):
            if any(', Show Conversation Details, Button' in i.get('caption','') for i in items):
                break
            items=self.native_items()
        headers=list(dict.fromkeys(i.get('caption','').split(', Show Conversation Details, Button')[0] for i in items if ', Show Conversation Details, Button' in i.get('caption','')))
        composers=[i.get('caption','') for i in items if i.get('caption','').startswith('Message, ')]
        if headers!=[contact] or not any(text in c for c in composers):
            raise ValueError('粘贴内容或联系人未确认，未点击发送')
        # Re-capture after accessibility traversal to avoid clicking a stale control position.
        fresh=self.frame()
        if image.size!=fresh.size:
            raise ValueError('画面尺寸变化，未发送')
        # The control stays put while input focus is unchanged; verify its colored center.
        sx,sy=circles[0];pixel=np.asarray(fresh)[round(sy*fresh.height),round(sx*fresh.width)].astype(int)
        if not ((pixel[2]-pixel[0]>60 and pixel[2]>140) or (pixel[1]-pixel[0]>50 and pixel[1]-pixel[2]>20)):
            # White arrow can occupy the centroid; verify the surrounding circular colored area instead.
            px,py=round(sx*fresh.width),round(sy*fresh.height)
            region=np.asarray(fresh)[max(0,py-20):py+21,max(0,px-20):px+21].astype(int)
            colored=((region[:,:,2]-region[:,:,0]>60)&(region[:,:,2]>140))|((region[:,:,1]-region[:,:,0]>50)&(region[:,:,1]-region[:,:,2]>20))
            if colored.mean()<.3:
                raise ValueError('发送控件已变化，未发送')
        self.tap(sx,sy)
        for attempt in range(3):
            time.sleep(.5)
            items=self.native_items()
            headers=list(dict.fromkeys(i.get('caption','').split(', Show Conversation Details, Button')[0] for i in items if ', Show Conversation Details, Button' in i.get('caption','')))
            if headers!=[contact]:
                raise ValueError('发送后联系人变化，结果需核对')
            if any(i.get('caption','').startswith(prefix+text+', ') for i in items for prefix in ('Your iMessage, ','Your Message, ','Your SMS, ')):
                return {'confirmed':True,'text':text}
        raise ValueError('未在系统短信描述中确认发送结果')


    def paste_text(self, text):
        # Paste through the text-field context menu. Keyboard candidate text is never used.
        self.request('/host-clipboard', {'text':text})
        self.request('/clipboard', {'text':text})
        board=self.request('/clipboard')
        if board.get('text')!=text:
            raise ValueError('手机剪贴板内容未确认，未粘贴')
        image=self.frame();lines=self.lines(image)
        fields=[l for l in lines if normalized(l['text']) in ('imessage','textmessage','message','短信','信息') and l['y']>image.height*.40 and l['x']>image.width*.15]
        if len(fields)!=1:
            raise ValueError('未定位空输入框，未覆盖已有草稿')
        field=fields[0];x=(field['x']+field['w']/2)/image.width;y=(field['y']+field['h']/2)/image.height
        coords={'x':round(x*65535),'y':round(y*65535)}
        try:
            self.request('/touch',{'type':'contact',**coords});time.sleep(1.1)
        finally:
            self.request('/touch',{'type':'release',**coords})
        time.sleep(.5)
        image=self.frame();lines=self.lines(image)
        image.save(ROOT/'diagnostics'/'paste-menu-current.png')
        choices=[l for l in lines if normalized(l['text']) in ('paste','粘贴','粘貼','贴上','貼上')]
        if len(choices)!=1:
            (ROOT/'diagnostics'/'paste-menu-lines.json').write_text(json.dumps(lines,ensure_ascii=False,indent=2),encoding='utf-8')
            raise ValueError('输入框的粘贴菜单未唯一定位，未参考输入法候选')
        choice=choices[0]
        self.tap((choice['x']+choice['w']/2)/image.width,(choice['y']+choice['h']/2)/image.height)
        items=self.native_items()
        if not any(i.get('caption','')=='Message, '+text or i.get('caption','').startswith('Message, '+text+', ') for i in items):
            raise ValueError('粘贴动作后输入框正文未确认，未发送')

