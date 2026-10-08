from pathlib import Path
p=Path('native_conversation.py')
s=p.read_text(encoding='utf-8-sig')
s=s.replace('return_after=False,exit_recipient_search=False):','return_after=False,exit_recipient_search=False,send_text=None):')
s=s.replace("    key=phone_key(query)","    if send_text is not None and (send_text!='Good night' or not confirm):raise ValueError('This demonstration only sends exact Good night after recipient confirmation')\n    key=phone_key(query)")
needle='            if return_after:\n'
insert='''            if send_text is not None:
                outgoing=lambda rows:[c for c in rows if re.match(r'^Your (?:iMessage|Message|Text Message), '+re.escape(send_text)+r', \\d{1,2}:\\d{2}(?:,|$)',c)]
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
'''
s=s.replace(needle,insert+needle)
s=s.replace("                if not any(c.startswith(('New iMessage, Show Conversation Details, Button','New Text Message, Show Conversation Details, Button','New Message, Show Conversation Details, Button')) for c in after) or not any(c in ('Message, iMessage','Message, Text Message','Message') for c in after) or any(c.startswith('Send, Button') for c in after):raise RuntimeError('Empty new conversation not confirmed; preserving draft')", "                if not any(c in ('Message, iMessage','Message, Text Message','Message') for c in after) or any(c.startswith('Send, Button') for c in after):raise RuntimeError('Empty composer not confirmed; preserving draft')")
s=s.replace("                if 'Unread, Header' not in returned:raise RuntimeError('Return to unread list not verified')", """                if 'Unread, Header' not in returned and any(', Show Conversation Details, Button' in c for c in returned):
                    try:
                        for n in range(19):
                            p.request(p.base,'/touch',{'type':'contact','x':round((.008+(.72-.008)*n/18)*65535),'y':32768});await asyncio.sleep(.025)
                    finally:p.request(p.base,'/touch',{'type':'release','x':round(.72*65535),'y':32768})
                    await asyncio.sleep(.5);returned=await page(s)
                if 'Unread, Header' not in returned:raise RuntimeError('Return to unread list not verified')""")
s=s.replace("parser.add_argument('--exit-recipient-search',action='store_true');args", "parser.add_argument('--exit-recipient-search',action='store_true');parser.add_argument('--send-text',choices=['Good night']);args")
s=s.replace('args.return_after,args.exit_recipient_search))','args.return_after,args.exit_recipient_search,args.send_text))')
p.write_text(s,encoding='utf-8')
