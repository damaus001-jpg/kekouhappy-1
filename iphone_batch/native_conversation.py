"""Open uniquely identified unread phone conversations via native keyboard navigation."""
import argparse,asyncio,json,re,sys,urllib.request
from pathlib import Path
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from pymobiledevice3.remote.core_device.hid_service import ASCII_TO_HID
from native_ui_scan import scan
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
DEVICE='00008030-001C481A3C32802E'
def phone_key(value):
    value=value.replace('\u200e','').strip()
    if not re.fullmatch(r'\+?[\d ()-]+',value):return None
    digits=re.sub(r'\D','',value)
    if value.startswith('+') and 7<=len(digits)<=15:return '+'+digits
    if len(digits)==10:return '+1'+digits
    if len(digits)==11 and digits.startswith('1'):return '+'+digits
    return None
class NativeConversation:
    def __init__(self):self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));self.base=None
    def request(self,base,path,body=None):
        r=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with self.opener.open(r,timeout=10) as response:raw=response.read()
        try:return json.loads(raw)
        except ValueError:return raw.decode()
    def select(self):
        state=self.request('http://127.0.0.1:8070','/api/state')
        device=next(d for d in state['devices'] if d['udid']==DEVICE and d['ready'])
        self.request('http://127.0.0.1:8070','/api/select',{'udid':DEVICE});self.base='http://127.0.0.1:'+str(device['port'])
    async def keys(self,keys):
        self.request(self.base,'/key',{'usages':keys});await asyncio.sleep(.12)
    async def chord(self,key):
        try:
            for keys in ([],[0xE3],[0xE3,key],[0xE3],[]):await self.keys(keys)
        finally:await self.keys([])
    async def text(self,value):
        try:
            for ch in value:
                usage,shift=ASCII_TO_HID[ch]
                await self.keys(([0xE1] if shift else [])+[usage]);await self.keys([])
        finally:await self.keys([])
    async def paste(self,value):
        self.request(self.base,'/clipboard',{'text':value});await self.chord(0x19)
async def page(s):return [i.caption or '' for i in await scan(s)]
async def run(query,confirm,return_after=False,exit_recipient_search=False,send_text=None):
    if send_text is not None and (send_text!='Good night' or not confirm):raise ValueError('This demonstration only sends exact Good night after recipient confirmation')
    key=phone_key(query)
    if key is None:raise ValueError('Use a complete phone number; names cannot uniquely identify recipients')
    ld=await create_using_usbmux(serial=DEVICE,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    p=NativeConversation()
    try:
        async with AccessibilityAudit(ld) as s:
            before=await page(s);p.select()
            if exit_recipient_search:
                for _ in range(2):
                    if not any(c.startswith('New Message, Show Conversation Details, Button') for c in before):break
                    if any(c.startswith('Send, Button') for c in before) or not any(c.startswith('To:') for c in before):raise RuntimeError('Cannot confirm uncommitted recipient search; preserving draft')
                    await p.keys([0x29]);await p.keys([]);await asyncio.sleep(.4);before=await page(s)
            if 'Unread, Header' not in before or any(', Show Conversation Details, Button' in c for c in before):raise RuntimeError('Start on unread list; existing conversations/drafts are preserved')
            matches=[c for c in before if ', Unread, ' in c and phone_key(c.split(', Unread, ')[0])==key]
            if len(matches)!=1:raise RuntimeError('Requested unread phone number is not unique in native list')
            print(json.dumps({'status':'unread_phone_confirmed','phone_key':key,'contact':matches[0]}),flush=True)
            await p.chord(0x11);await asyncio.sleep(.4);opened=await page(s)
            if not any(c.startswith('New Message, Show Conversation Details, Button') for c in opened) or 'To:' not in opened or 'Message' not in opened:raise RuntimeError('Empty recipient entry not confirmed')
            await p.paste(key);await asyncio.sleep(.4);entered=await page(s)
            if not any(c.startswith('To:, ') and phone_key(c[5:])==key for c in entered):raise RuntimeError('Pasted number not verified; Return prohibited')
            print(json.dumps({'status':'recipient_number_verified','phone_key':key}),flush=True)
            if not confirm:return
            await p.keys([0x28]);await p.keys([]);await asyncio.sleep(.6);after=await page(s)
            recipient_rows=[c for c in after if ', Button' in c and any(phone_key(part)==key for part in c.split(', '))]
            bubbles=[c for c in after if c.startswith(('Your iMessage, ','Your Message, ')) or (phone_key(c.split(', ')[0])==key and re.search(r', \d{1,2}:\d{2}(?:,|$)',c))]
            if not recipient_rows or not bubbles:raise RuntimeError('Existing conversation identity/history not verified; stopped without sending')
            print(json.dumps({'status':'existing_conversation_verified','phone_key':key,'recipient_elements':recipient_rows,'bubble_count':len(bubbles),'send_clicked':False}),flush=True)
            (ROOT/'diagnostics'/'native-conversation-verified.json').write_text(json.dumps({'phone_key':key,'captions':after},ensure_ascii=False,indent=2),encoding='utf-8')
            if send_text is not None:
                outgoing=lambda rows:[c for c in rows if re.match(r'^Your (?:iMessage|Message|Text Message), '+re.escape(send_text)+r', \d{1,2}:\d{2}(?:,|$)',c)]
                baseline=outgoing(after)
                if baseline:raise RuntimeError('Same demo text already exists; stopped to prevent duplicate sends')
                if not any(c in ('Message, iMessage','Message, Text Message','Message') for c in after) or any(c.startswith('Send, Button') for c in after):raise RuntimeError('Composer is not confirmed empty; existing draft preserved')
                await p.keys([0x2B]);await p.keys([])
                await p.paste(send_text);await asyncio.sleep(.5);prepared=await page(s)
                if 'Message, '+send_text not in prepared or not any(c.startswith('Send, Button') for c in prepared) or not any(', Button' in c and any(phone_key(part)==key for part in c.split(', ')) for c in prepared):raise RuntimeError('Exact recipient and uppercase Good night composer not confirmed; no send')
                print(json.dumps({'status':'exact_reply_prepared','phone_key':key,'text':send_text}),flush=True)
                receipt=ROOT/'diagnostics'/('native-send-'+key[1:]+'.json')
                if receipt.exists():raise RuntimeError('A previous send attempt exists for this number; no automatic retry')
                receipt.write_text(json.dumps({'status':'send_requested','phone_key':key,'text':send_text}),encoding='utf-8')
                await p.keys([0x28]);await p.keys([]);await asyncio.sleep(1);after=await page(s)
                new_messages=outgoing(after)
                if not new_messages or 'Message, '+send_text in after:raise RuntimeError('Send result uncertain; no retry')
                receipt.write_text(json.dumps({'status':'sent_verified','phone_key':key,'text':send_text,'new_message_elements':new_messages,'captions':after},ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({'status':'sent_verified','phone_key':key,'text':send_text,'new_message_elements':new_messages}),flush=True)
            if return_after:
                if not any(c in ('Message, iMessage','Message, Text Message','Message') for c in after) or any(c.startswith('Send, Button') for c in after):raise RuntimeError('Empty composer not confirmed; preserving draft')
                await p.keys([0x29]);await p.keys([]);await asyncio.sleep(.4);returned=await page(s)
                if 'Unread, Header' not in returned and any(', Show Conversation Details, Button' in c for c in returned):
                    try:
                        for n in range(19):
                            p.request(p.base,'/touch',{'type':'contact','x':round((.008+(.72-.008)*n/18)*65535),'y':32768});await asyncio.sleep(.025)
                    finally:p.request(p.base,'/touch',{'type':'release','x':round(.72*65535),'y':32768})
                    await asyncio.sleep(.5);returned=await page(s)
                if 'Unread, Header' not in returned:raise RuntimeError('Return to unread list not verified')
                print(json.dumps({'status':'returned_to_unread_list','remaining_unread':[c for c in returned if ', Unread, ' in c],'send_clicked':False}),flush=True)
    finally:await ld.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--query',required=True);parser.add_argument('--confirm-recipient',action='store_true');parser.add_argument('--return-after',action='store_true');parser.add_argument('--exit-recipient-search',action='store_true');parser.add_argument('--send-text',choices=['Good night']);args=parser.parse_args()
    if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run(args.query,args.confirm_recipient,args.return_after,args.exit_recipient_search,args.send_text))
