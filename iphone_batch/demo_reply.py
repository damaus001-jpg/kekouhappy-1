"""One explicitly authorized emoji demonstration. No model or translation API."""
import json
import time
from reply_assistant import ReplyAssistant
from reply_phone import PhoneDriver, ROOT
from sms_collect import TIME

class DemoPhone(PhoneDriver):
    demo=True
    def find_unread(self,stop=None):
        image=self.frame();lines=self.lines(image)
        if not any(line['text'].strip().lower() in ('unread','未读','未讀') and line['y']<image.height*.15 for line in lines):
            raise ValueError('请停留在未读列表')
        rows=self.unread_rows(image,lines)
        candidates=rows
        return candidates[0] if candidates else None
    def read_context(self):
        items=self.native_items()
        for _ in range(2):
            if any(', Show Conversation Details, Button' in i.get('caption','') for i in items):
                break
            items=self.native_items()
        contacts=[item.get('caption','').split(', Show Conversation Details, Button')[0] for item in items if ', Show Conversation Details, Button' in item.get('caption','')]
        contacts=list(dict.fromkeys(contacts))
        if len(contacts)!=1:
            raise ValueError('未确认唯一的会话联系人')
        contact=contacts[0];messages=[]
        for item in items:
            caption=item.get('caption') or '';match=TIME.search(caption)
            text=caption[:match.start()] if match else caption
            for prefix,side in [('Your iMessage, ','outgoing'),('Your Message, ','outgoing'),('Your SMS, ','outgoing'),(contact+', ','incoming')]:
                if text.startswith(prefix):
                    messages.append({'side':side,'text':text[len(prefix):],'time':match[1] if match else None});break
        path=ROOT/'diagnostics'/'demo-context-current.json'
        path.write_text(json.dumps({'contact':contact,'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
        return {'contact':contact,'messages':[],'source':'identity-only-emoji-demo-no-translation'}

class DemoModel:
    def suggest(self,contact,messages,settings):
        return {'summary_zh':'动作演示，不调用翻译或模型服务','incoming_translations':[],
            'allow_auto':False,'suggestions':[{'text':text,'meaning_zh':'演示表情','reason_zh':'用于验证发送动作'} for text in ('good night','Good night!','Have a good night!')]}

def main():
    device='00008030-001C481A3C32802E'
    driver=DemoPhone();assistant=ReplyAssistant(driver,model=DemoModel());assistant.device=device
    print(json.dumps({'status':'demo_start','reply':'good night','max_sends':1}),flush=True)
    task=assistant._discover()
    if task is None:
        raise ValueError('没有找到适合演示的未读会话，未发送')
    print(json.dumps({'status':'conversation_opened','task_id':task['id'],'messages':len(task['messages'])}),flush=True)
    time.sleep(2)
    sent=assistant.send(task['id'],0)
    print(json.dumps({'status':'demo_finished','task_id':sent['id'],'reply':sent['sent_text'],'note':assistant.message}),flush=True)

if __name__=='__main__':main()

