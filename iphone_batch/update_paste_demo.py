from pathlib import Path
p=Path('iphone_batch/reply_phone.py')
s=p.read_text(encoding='utf-8-sig')
s=s.replace("l['y']>image.height*.65", "l['y']>image.height*.40")
s=s.replace("        self.request('/clipboard',{'text':text});self.keys([0xE3,0x19])", "        self.paste_text(text)")
s=s.replace("mask[:,:int(image.width*.80)]=0", "mask[:,:int(image.width*.02)]=0")
s=s.replace("if .035*image.width<w<.10*image.width and .75<w/h<1.3 and area>w*h*.45:", "if x>image.width*.80 and .035*image.width<w<.10*image.width and .75<w/h<1.3 and area>w*h*.45:")
s=s.replace("        items=self.native_items()\n        headers=", "        items=self.native_items()\n        for _ in range(2):\n            if any(', Show Conversation Details, Button' in i.get('caption','') for i in items):\n                break\n            items=self.native_items()\n        headers=")
s=s.replace("headers=[i.get('caption','').split(', Show Conversation Details, Button')[0] for i in items if ', Show Conversation Details, Button' in i.get('caption','')]", "headers=list(dict.fromkeys(i.get('caption','').split(', Show Conversation Details, Button')[0] for i in items if ', Show Conversation Details, Button' in i.get('caption','')))")
addition='''
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
'''
s+=addition
p.write_text(s,encoding='utf-8')
p=Path('iphone_batch/demo_reply.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("candidates=[row for row in rows if 'wrong number' not in row['preview'].lower()]", "candidates=rows")
s=s.replace("('🙂','😀','👍')", "('good night','Good night!','Have a good night!')")
s=s.replace("'reply':'🙂'", "'reply':'good night'")
p.write_text(s,encoding='utf-8')
p=Path('iphone_batch/probe_video_frame.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("            print(json.dumps({'image':str(output),'width':frames[-1].width,'height':frames[-1].height}))\n            if time.monotonic()-started >= 3:\n                break", "            if time.monotonic()-started >= 3:\n                print(json.dumps({'image':str(output),'width':frames[-1].width,'height':frames[-1].height}))\n                break")
p.write_text(s,encoding='utf-8')
