let workspaceDevice=null, workspaceRevision=0, savedConversations=[], currentConversation=null;
let currentConversationId=null;
let workspaceBusy=false, generatedDraft=null;
let pastedEnglish=false;
let sendBlocked=false;
let phonePastePending=null;
const notificationProtection=new Map();
function protectNotificationDraft(){
 if(!workspaceDevice)return;
 const protectedDraft=!!(draftEl.value.trim()||generatedDraft||workspaceBusy);
 if(notificationProtection.get(workspaceDevice)===protectedDraft)return;
 notificationProtection.set(workspaceDevice,protectedDraft);
 fetch('/api/notification-policy',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({device:workspaceDevice,protected:protectedDraft})}).then(response=>{
   if(!response.ok)notificationProtection.delete(workspaceDevice);
  }).catch(()=>notificationProtection.delete(workspaceDevice));
}
const messagesEl=document.getElementById('messages'), draftEl=document.getElementById('reply-zh');
function scrollReadingToBottom(){
 // Follow the new bubble inside the reading pane without scrolling the page
 // or moving the adjacent live phone screen out of the user's view.
 messagesEl.scrollTop=messagesEl.scrollHeight;
}
function draftKey(){const device=workspaceDevice||(typeof devicePreview!=='undefined'&&devicePreview?'preview:'+active:'');return 'sms-draft:'+device+':'+(currentConversation?.contact||window.ForegroundSync?.number||'');}
function resizeDraft(){draftEl.style.height='auto';draftEl.style.height=Math.min(draftEl.scrollHeight||44,128)+'px';}
const emojiPicker=document.getElementById('emoji-picker'),emojiToggle=document.getElementById('toggle-emoji');
let emojiFloating=false;
function closeEmojiPicker(){
 emojiPicker.hidden=true;emojiToggle.setAttribute('aria-expanded','false');
 if(emojiFloating){emojiToggle.parentElement.append(emojiPicker);emojiPicker.classList.remove('emoji-floating');emojiFloating=false;}
}
function positionEmojiPicker(){
 if(emojiPicker.hidden)return;
 const bounds=emojiToggle.getBoundingClientRect(),width=Math.min(288,window.innerWidth-24);
 emojiPicker.style.width=width+'px';emojiPicker.style.maxHeight=Math.max(100,window.innerHeight-24)+'px';
 emojiPicker.style.left=Math.max(12,Math.min(bounds.left,window.innerWidth-width-12))+'px';
 emojiPicker.style.top=Math.max(12,bounds.top-emojiPicker.getBoundingClientRect().height-8)+'px';
}
for(const emoji of ['😀','😃','😄','😁','😊','🙂','😉','😍','🥰','😘','😂','🤣','😅','😎','🤔','🙏','👍','👎','👏','🙌','🤝','👋','💪','❤️','🧡','💛','💚','💙','💜','💕','💖','🎉','🎂','🌹','🌷','🌸','🌺','🌻','🌼','💐','🥀','🌿','🍀','☀️','🌙','✨','🔥','✅']){
 const button=document.createElement('button');button.type='button';button.textContent=emoji;button.setAttribute('aria-label',emoji);button.setAttribute('data-emoji',emoji);
 button.addEventListener('pointerdown',event=>event.preventDefault());
 button.addEventListener('click',()=>{
  if(draftEl.disabled){notice('请先选择手机并读取联系人会话，再插入表情。');return;}
  const start=draftEl.selectionStart??draftEl.value.length,end=draftEl.selectionEnd??start;
  draftEl.setRangeText(emoji,start,end,'end');
  draftEl.dispatchEvent(new Event('input',{bubbles:true}));draftEl.focus();closeEmojiPicker();
 });emojiPicker.append(button);
}
emojiToggle.addEventListener('click',()=>{
 if(emojiToggle.disabled)return;
 if(!emojiPicker.hidden){closeEmojiPicker();return;}
 document.body.append(emojiPicker);emojiPicker.classList.add('emoji-floating');emojiFloating=true;
 emojiPicker.hidden=false;emojiToggle.setAttribute('aria-expanded','true');positionEmojiPicker();
});
document.addEventListener('pointerdown',event=>{if(!emojiPicker.contains(event.target)&&!emojiToggle.contains(event.target))closeEmojiPicker();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeEmojiPicker();});
window.addEventListener('resize',positionEmojiPicker);
document.addEventListener('scroll',positionEmojiPicker,true);
function notice(text){
 const monitorNotice=document.getElementById('monitor-notice');
 const passive=/^(仅显示所选手机的保存记录|选择手机后加载|正在加载已保存|已保存记录)/.test(text)||text===currentConversation?.scope;
 if(monitorNotice&&(!passive||!monitorNotice.dataset.operation)){
  monitorNotice.textContent=text;
  if(/^设备\s/.test(text))monitorNotice.dataset.operation='true';
 }
}
// Local submission receipts stay separate from phone observations and exports.
const outgoingReceiptCache=new Map();
let readingKeySerial=0;
function readingPhoneClock(row){
 const values=String(row.time||'').includes('T')?[row.date_label]:[row.time,row.date_label];
 for(const value of values){
  const match=String(value||'').match(/(?:^|\s)(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap]m)?$/i);
  if(match){let hour=Number(match[1]);if(match[3])hour=hour%12+(match[3].toLowerCase()==='pm'?12:0);return hour*60+Number(match[2]);}
 }
 return null;
}
function readingRowsMatch(a,b){
 const before=readingPhoneClock(a),after=readingPhoneClock(b);
 if(before!==null&&after!==null&&before!==after)return false;
 if(a.date&&b.date&&a.date.slice(-5)!==b.date.slice(-5))return false;
 return a.text===b.text&&(a.kind||'text')===(b.kind||'text')&&
  (a.side===b.side||a.side==='unknown'||b.side==='unknown');
}
function readingRowKey(row){return row.reading_key||(row.reading_key='reading:'+ ++readingKeySerial);}
function overlayReadingRow(old,observed){
 const row={...old,...observed,reading_key:readingRowKey(old)};
 if(['incoming','outgoing'].includes(old.side)&&!['incoming','outgoing'].includes(observed.side))row.side=old.side;
 // Database timestamps and phone clocks have different formats/timezones.
 // Keep already displayed, known metadata until a previously missing field is filled.
 if(!old.reading_pending)for(const field of ['time','date','date_label','date_precision','date_year','date_source']){
  if(old[field]!==undefined&&old[field]!==null&&old[field]!=='')row[field]=old[field];
 }
 const oldRelative=String(old.date_label||'').match(/^(Today|Yesterday|今天|昨天)(?=\s|$)/i);
 const newRelative=String(observed.date_label||'').match(/^(Today|Yesterday|今天|昨天)(?=\s|$)/i);
 if(oldRelative&&newRelative&&oldRelative[1].toLowerCase()!==newRelative[1].toLowerCase()&&!observed.reading_pending)row.date_label=observed.date_label;
 if(observed.bubble_status){
  row.bubble_status={...old.bubble_status,...observed.bubble_status};
  if(observed.bubble_status.delivery&&!observed.bubble_status.read_time)delete row.bubble_status.read_time;
 }
 if(observed.reading_pending!==true&&['incoming','outgoing'].includes(observed.side)&&observed.time)delete row.reading_pending;
 if(!old.reading_pending&&['incoming','outgoing'].includes(old.side)&&old.time)delete row.reading_pending;
 return row;
}
function mergeReadingRows(existing,incoming,{progress=false}={}){
 if(!existing.length)return incoming.map(row=>({...row,reading_key:readingRowKey(row)}));
 if(!incoming.length)return existing;
 const positions=(haystack,needle)=>{
  const found=[];
  for(let i=0;i<=haystack.length-needle.length;i++)if(needle.every((row,j)=>readingRowsMatch(haystack[i+j],row)))found.push(i);
  return found;
 };
 const inside=positions(existing,incoming);
 if(inside.length===1){
  const rows=existing.slice();incoming.forEach((row,i)=>{rows[inside[0]+i]=overlayReadingRow(rows[inside[0]+i],row);});return rows;
 }
 const around=positions(incoming,existing);
 if(around.length===1)return incoming.map((row,i)=>i>=around[0]&&i<around[0]+existing.length?
  overlayReadingRow(existing[i-around[0]],row):{...row,reading_key:readingRowKey(row)});
 for(let size=Math.min(existing.length,incoming.length);size>0;size--){
  const suffix=existing.slice(-size),prefix=existing.slice(0,size);
  if(suffix.every((row,i)=>readingRowsMatch(row,incoming[i]))&&positions(existing,suffix).length===1&&positions(incoming,suffix).length===1)
   return existing.slice(0,-size).concat(incoming.map((row,i)=>i<size?overlayReadingRow(suffix[i],row):{...row,reading_key:readingRowKey(row)}));
  if(prefix.every((row,i)=>readingRowsMatch(row,incoming[incoming.length-size+i]))&&positions(existing,prefix).length===1&&positions(incoming,prefix).length===1)
   return incoming.slice(0,-size).map(row=>({...row,reading_key:readingRowKey(row)})).concat(prefix.map((row,i)=>overlayReadingRow(row,incoming[incoming.length-size+i])),existing.slice(size));
 }
 if(!progress&&incoming.length>=existing.length){
  const used=new Set();
  return incoming.map(row=>{
   const index=existing.findIndex((old,i)=>!used.has(i)&&readingRowsMatch(old,row));
   if(index<0)return {...row,reading_key:readingRowKey(row)};
   used.add(index);return overlayReadingRow(existing[index],row);
  });
 }
 // An incomplete window never erases known history. Show newly observed bodies
 // without collapsing genuine repeated occurrences inside the incoming window.
 return existing.concat(incoming.filter(row=>!existing.some(old=>readingRowsMatch(old,row)))
  .map(row=>({...row,reading_key:readingRowKey(row)})));
}
function outgoingReceiptKey(device,number){return 'sms-outgoing:'+JSON.stringify([device,String(number||'').replace(/\D/g,'')]);}
function outgoingReceipts(device,number){
 const key=outgoingReceiptKey(device,number);
 if(!outgoingReceiptCache.has(key)){
  let receipts=[];
  try{const saved=JSON.parse(localStorage.getItem(key)||'[]');if(Array.isArray(saved))receipts=saved.filter(r=>r&&typeof r.id==='string'&&typeof r.text==='string'&&Array.isArray(r.baseline));}catch{}
  outgoingReceiptCache.set(key,receipts);
 }
 return outgoingReceiptCache.get(key);
}
function saveOutgoingReceipts(device,number,receipts){
 const key=outgoingReceiptKey(device,number);outgoingReceiptCache.set(key,receipts);
 try{if(receipts.length)localStorage.setItem(key,JSON.stringify(receipts));else localStorage.removeItem(key);}catch{}
}
function outgoingMessageKey(message){return JSON.stringify([message.side,message.text,message.time||null,message.kind||'text']);}
function outgoingBaseline(device,number){
 if(device!==workspaceDevice||String(currentConversation?.phone_number||'').replace(/\D/g,'')!==String(number||'').replace(/\D/g,''))return [];
 return (currentConversation?.messages||[]).slice(-8).map(outgoingMessageKey);
}
function acknowledgeOutgoing(receipt){
 const {device,number,id,text}=receipt;
 if(!device||!number||!id||typeof text!=='string'||!text.trim())return false;
 const receipts=outgoingReceipts(device,number);
 if(receipts.some(r=>r.id===id))return false;
 receipts.push({id,text,submitted_at:new Date().toISOString(),baseline:receipt.baseline||outgoingBaseline(device,number)});
 saveOutgoingReceipts(device,number,receipts);return true;
}
function readingOutgoingRows(device,number,rows){
 rows=rows.slice();
 if(!device||!number)return rows;
 const receipts=outgoingReceipts(device,number);
 if(!receipts.length)return rows;
 const keys=rows.map(outgoingMessageKey),remaining=[],used=new Set();
 let lastMatched=-1;
 for(const receipt of receipts){
  let start=null;
  for(let size=receipt.baseline.length;size>0;size--){
   const suffix=receipt.baseline.slice(-size),positions=[];
   for(let i=0;i<=keys.length-size;i++)if(suffix.every((key,j)=>keys[i+j]===key))positions.push(i+size);
   if(positions.length){if(positions.length===1)start=positions[0];break;}
  }
  // No baseline means an old identical bubble cannot prove this submission.
  const match=start===null?-1:rows.findIndex((m,i)=>i>=start&&!used.has(i)&&m.side==='outgoing'&&m.text===receipt.text);
  if(match>=0){rows[match].reading_key='pending:'+receipt.id;used.add(match);lastMatched=Math.max(lastMatched,match);continue;}
  if(start!==null&&lastMatched>=start)receipt.baseline=keys.slice(0,lastMatched+1).slice(-8);
  remaining.push(receipt);
 }
 saveOutgoingReceipts(device,number,remaining);
 return rows.concat(remaining.map(receipt=>{
  const submitted=new Date(receipt.submitted_at);
  return {side:'outgoing',kind:'text',text:receipt.text,time:submitted.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}),
   date_label:submitted.getFullYear()+'年'+(submitted.getMonth()+1)+'月'+submitted.getDate()+'日',
   local_outgoing_id:receipt.id,reading_key:'pending:'+receipt.id,record_source:'local-submission'};
 }));
}
const monthNumbers=Object.fromEntries('jan feb mar apr may jun jul aug sep oct nov dec'.split(' ').map((m,i)=>[m,i+1]));
const chineseWeekdays={sun:'周日',mon:'周一',tue:'周二',wed:'周三',thu:'周四',fri:'周五',sat:'周六'};
function readingDateLabel(message){
 const raw=(message.date_label||'').replace(/[\u200e\u200f]/g,'').trim();
 const clock=raw.match(/\s+(?:at\s+)?(\d{1,2}):(\d{2})(?:\s*([ap]m))?$/i);
 let clockText='';
 if(clock){
  let hour=Number(clock[1]);
  if(clock[3])hour=hour%12+(clock[3].toLowerCase()==='pm'?12:0);
  clockText=' '+String(hour).padStart(2,'0')+':'+clock[2];
 }
 const day=clock?raw.slice(0,clock.index).trim():raw;
 if(/^(今天|昨天|前天|(?:星期|周)[一二三四五六日天]|(?:\d{4}年)?\d{1,2}月\d{1,2}[日号])/.test(day))return day+clockText;
 const relative={today:'今天',yesterday:'昨天'}[day.toLowerCase()];
 if(relative)return relative+clockText;
 const weekday=chineseWeekdays[day.slice(0,3).toLowerCase()];
 if(weekday&&/^[a-z]+$/i.test(day))return weekday+clockText;
 const named=day.match(/^(?:([a-z]+),?\s+)?([a-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?$/i);
 if(named){
  const month=monthNumbers[named[2].slice(0,3).toLowerCase()];
  const week=chineseWeekdays[(named[1]||'').slice(0,3).toLowerCase()];
  if(month)return (named[4]?named[4]+'年':'')+month+'月'+Number(named[3])+'日'+(week?' '+week:'')+clockText;
 }
 const stored=message.date||day;
 const numeric=stored.match(/^(?:(\d{4})[-/])?(\d{1,2})[-/](\d{1,2})$/);
 return numeric?(numeric[1]?numeric[1]+'年':'')+Number(numeric[2])+'月'+Number(numeric[3])+'日'+clockText:'';
}
function readingBubbleStatus(message){
 if(message.reading_pending)return '字段待核对';
 if(message.side!=='outgoing')return '';
 if(message.local_outgoing_id)return '已提交，待核对';
 const status=message.bubble_status||{};
 const method={sms:'以短信形式发送',rcs:'以 RCS 形式发送'}[status.sending_method];
 const delivery={not_delivered:'未送达',delivered:'已送达',read:'已读'}[status.delivery];
 const receipt=delivery?delivery+(delivery==='已读'&&status.read_time?' '+status.read_time:''):'';
 return [method,receipt].filter(Boolean).join(' · ');
}
function renderConversation({preserveInput=false}={}){
 closeEmojiPicker();
 if(!preserveInput){
  sendBlocked=false;
  document.getElementById('send-reply').textContent='确认发送';
  pastedEnglish=false;
  generatedDraft=null;
 }
 currentConversation=savedConversations.find(c=>c.id===currentConversationId)||null;
 if(typeof refreshContactProfile==='function')refreshContactProfile();
 const readingNumber=currentConversation?.phone_number||window.ForegroundSync?.number;
 document.getElementById('peer-phone').textContent=readingNumber||'—';
 if(typeof syncContactFollowup==='function')syncContactFollowup();
 const contactKey=outgoingReceiptKey(workspaceDevice,readingNumber);
 const reuse=messagesEl.dataset.readingContact===contactKey;
 const oldMessages=new Map(reuse?Array.from(messagesEl.querySelectorAll('.message'),node=>[node.dataset.readingKey,node]):[]);
 const oldDates=new Map(reuse?Array.from(messagesEl.querySelectorAll('.message-date'),node=>[node.dataset.readingDate,node]):[]);
 const nextNodes=[];
 messagesEl.dataset.readingContact=contactKey;
 draftEl.disabled=workspaceBusy;
 if(!preserveInput)try{draftEl.value=currentConversation?localStorage.getItem(draftKey())||'':'';}catch{draftEl.value='';}
 const rows=readingOutgoingRows(workspaceDevice,readingNumber,currentConversation?.messages||[]);
 syncWorkspaceControls();
 document.getElementById('message-count').textContent=rows.length+' 条记录';
 if(!rows.length){const empty=document.createElement('div');empty.className='message-empty';empty.textContent='尚无当前手机的保存记录。读取当前会话后显示短信原文。';messagesEl.replaceChildren(empty);notice('仅显示所选手机的保存记录，不是手机当前会话的实时同步。');return;}
 const peerNumber=String(currentConversation?.phone_number||currentConversation?.contact||'').trim();
 let previousDate='';const dateCounts=new Map();
 for(const [index,message] of rows.entries()){
  // Backup timestamps already carry an offset. Preserve their recorded day
  // and timezone even when the workstation is in a different timezone.
  const iso=typeof message.time==='string'&&message.time.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/);
  const date=readingDateLabel(message)||(iso?iso[1]+'年'+Number(iso[2])+'月'+Number(iso[3])+'日':'');
  let time=iso?iso[4]+' UTC'+(['Z','+00:00'].includes(iso[5])?'':iso[5]):message.time;
  const clock=!iso&&typeof time==='string'&&time.match(/^(\d{1,2}):(\d{2})\s*([ap]m)?$/i);
  if(clock){let hour=Number(clock[1]);if(clock[3])hour=hour%12+(clock[3].toLowerCase()==='pm'?12:0);time=String(hour).padStart(2,'0')+':'+clock[2];}
  if(date!==previousDate){
   const count=(dateCounts.get(date)||0)+1;dateCounts.set(date,count);
   const dateKey=JSON.stringify([date,count]);
   const separator=oldDates.get(dateKey)||document.createElement('div');separator.className='message-date';separator.dataset.readingDate=dateKey;
   if(separator.textContent!==(date||'日期待确认'))separator.textContent=date||'日期待确认';
   nextNodes.push(separator);
  }
  previousDate=date;
  const key=readingRowKey(message),node=oldMessages.get(key)||document.createElement('div');
  if(!node.classList.contains('message'))node.classList.add('message');
  const outgoing=message.side==='outgoing';
  if(node.classList.contains('outgoing')!==outgoing)node.classList.toggle('outgoing',outgoing);
  if(node.classList.contains('incoming')===outgoing)node.classList.toggle('incoming',!outgoing);
  node.dataset.readingKey=key;if(node.dataset.messageId!==String(index))node.dataset.messageId=index;
  let meta=node.querySelector('.message-meta'),bubble=node.querySelector('.bubble'),original=node.querySelector('.original');
  if(!meta){meta=document.createElement('div');meta.className='message-meta';node.append(meta);}
  if(!bubble){bubble=document.createElement('div');bubble.className='bubble';node.append(bubble);}
  if(!original){original=document.createElement('div');original.className='original';bubble.append(original);}
  const metaText=(message.side==='outgoing'?'我方':message.side==='incoming'?'对方':'待核对')+' · '+(time||'时间未知')+(message.side==='incoming'&&peerNumber?' · '+peerNumber:'');
  if(meta.textContent!==metaText)meta.textContent=metaText;
  const body=message.text||(message.kind==='attachment'?'[附件消息]':message.decode_error?'[正文解析未完成]':'[无文字内容]');
  if(original.textContent!==body)original.textContent=body;
  const statusText=readingBubbleStatus(message);
  let status=node.querySelector('.message-status');
  if(statusText){
   if(!status){status=document.createElement('div');node.append(status);}
   const statusClass='message-status'+(message.bubble_status?.delivery==='not_delivered'?' failed':'');
   if(status.className!==statusClass)status.className=statusClass;
   if(status.textContent!==statusText)status.textContent=statusText;
  }else if(status)status.remove();
  nextNodes.push(node);
 }
 let cursor=messagesEl.firstChild;
 for(const node of nextNodes){if(node===cursor)cursor=cursor.nextSibling;else messagesEl.insertBefore(node,cursor);}
 while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
 notice(currentConversation.scope||('已保存记录 · '+(currentConversation.created||'时间未知')+' · 非实时同步，重复记录保留，历史完整性待核对。'));
}
async function loadWorkspace(device,force=false,preferred=null){
 if(!force&&workspaceDevice===device)return;
 const sameDevice=workspaceDevice===device,previousConversation=currentConversation;
 const requested=preferred||(workspaceDevice===device?currentConversationId:null);
 workspaceDevice=device;const revision=++workspaceRevision;
 if(!sameDevice){savedConversations=[];currentConversation=null;currentConversationId=null;renderConversation();}
 if(!device){notice('选择手机后加载已保存的短信原文。');return;}
 notice('正在加载已保存的短信原文…');
 try{const r=await fetch('/api/messages?device='+encodeURIComponent(device),{cache:'no-store'});const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'读取失败');if(revision!==workspaceRevision)return;
  savedConversations=data.conversations||[];
  currentConversationId=savedConversations.some(c=>c.id===requested)?requested:
   (sameDevice?savedConversations.find(c=>c.phone_number===previousConversation?.phone_number)?.id:null)||savedConversations[0]?.id||null;
  const selected=savedConversations.find(c=>c.id===currentConversationId);
  const sameContact=sameDevice&&selected&&selected.phone_number===previousConversation?.phone_number;
  if(sameContact)selected.messages=mergeReadingRows(previousConversation.messages,selected.messages);
  renderConversation({preserveInput:!!sameContact});
 }catch(e){if(revision===workspaceRevision)notice('记录读取失败：'+e.message);}
}
document.getElementById('refresh-messages').addEventListener('click',()=>loadWorkspace(workspaceDevice,true));
draftEl.addEventListener('input',()=>{
 window.ForegroundSync?.activity('draft');
 generatedDraft=null;syncWorkspaceControls();
 try{localStorage.setItem(draftKey(),draftEl.value);}catch{notice('浏览器未保存草稿。');}
});

function syncWorkspaceControls(){
 if(typeof syncDeviceRefreshControls==='function')syncDeviceRefreshControls();
 if(typeof sendFocus==='function')for(const card of cards.values()){
  if(card.lastWorking!==workspaceBusy){sendFocus(card,card.lastActive===true);card.lastWorking=workspaceBusy;}
 }
 const selected=!!workspaceDevice&&(typeof controlOwner==='undefined'||controlOwner===workspaceDevice), available=!!currentConversation&&!currentConversation.ui_reading;
 for(const id of ['capture-current','sync-full-history','refresh-messages'])document.getElementById(id).disabled=workspaceBusy||!selected;
 if(typeof syncContactProfileControls==='function')syncContactProfileControls();
 const sendButton=document.getElementById('send-reply');
 const pasteButton=document.getElementById('paste-to-phone');
 if(pasteButton)pasteButton.disabled=workspaceBusy||!!phonePastePending||!selected||!replyInputAvailable()||!draftEl.value.trim();
 sendButton.disabled=workspaceBusy||!!phonePastePending||sendBlocked||!selected||!replyInputAvailable()||!available||!draftEl.value.trim();
 const sendLabel=workspaceBusy?'正在处理':sendBlocked?'请先核对发送结果':'发送回复';
 sendButton.title=sendLabel;sendButton.setAttribute('aria-label',sendLabel);
 draftEl.disabled=workspaceBusy;
 emojiToggle.disabled=workspaceBusy;
 if(emojiToggle.disabled)closeEmojiPicker();
 resizeDraft();
 if(typeof renderFollowupContacts==='function')renderFollowupContacts();
 protectNotificationDraft();
}
async function workspaceRequest(action, extra={}, device=workspaceDevice){
 const r=await fetch('/api/workspace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,device,...extra})});
 const data=await r.json();
 if(!r.ok||data.error){
  const error=Error(data.error||'请求失败');
  error.beforeSend=action==='send'&&data.error==='未定位到唯一可用的手机发送按钮，未执行发送';
  throw error;
 }
 return data;
}
async function operation(text, action){
 if(workspaceBusy)return;
 window.ForegroundSync?.activity('manual');
 const sendButton=document.getElementById('send-reply');
 workspaceBusy=true;syncWorkspaceControls();notice(text);
 try{await action();}catch(e){
  if(e.beforeSend===true){sendBlocked=false;generatedDraft=null;}
  notice(e.message+(e.beforeSend===true?'；正文已保留，可再次手动发送。':''));
  if(sendBlocked)sendButton.textContent='发送未完成';
 }
 finally{workspaceBusy=false;if(!sendBlocked)sendButton.textContent='确认发送';else if(sendButton.textContent==='正在核验…')sendButton.textContent='发送已处理';syncWorkspaceControls();}
}
async function captureConversation(full=false){
 const device=workspaceDevice, revision=workspaceRevision;
 operation(full?'正在同步手机短信数据库，可能需要较长时间…':'正在回到底部并读取当前会话…',async()=>{
  const watch=window.ForegroundSync?.beginProgress?.();
  try{
   const result=await workspaceRequest('capture',full?{full:true}:{},device);if(revision!==workspaceRevision)return;
   await loadWorkspace(device,true,result.conversation_id);
   notice('已读取 '+result.contact+'；'+(result.scope||'历史范围待核对')+'。');
  }finally{if(watch)window.ForegroundSync?.endProgress?.(watch);}
 });
}
document.getElementById('capture-current').addEventListener('click',()=>captureConversation(false));
document.getElementById('sync-full-history').addEventListener('click',()=>captureConversation(true));
function showSentReply(result){
 if(result.conversation){
  const conversation=result.conversation;
  savedConversations=savedConversations.filter(c=>c.id!==conversation.id);
  savedConversations.unshift(conversation);
  currentConversationId=conversation.id;
  renderConversation();
  scrollReadingToBottom();
 }
 if(result.reading_error)notice('发送已确认；阅读区更新失败：'+result.reading_error+'。请读取当前会话，勿重复发送。');
}
function replyInputAvailable(){
 if(typeof cards==='undefined')return true;
 const card=cards.get(workspaceDevice);
 return !card||card.inputReady===true;
}
function replyControlAvailable(){
 if(!workspaceDevice){notice('请先选择手机，再发送回复。');return false;}
 if(typeof controlOwner!=='undefined'&&controlOwner!==workspaceDevice){notice('当前手机尚未取得控制权，请点选该手机，恢复投屏控制后再发送。');return false;}
 if(!replyInputAvailable()){notice('当前手机控制连接不可用，请刷新设备列表，恢复后再发送。');return false;}
 return true;
}
document.getElementById('send-reply').addEventListener('click',submitReplyInput);
function pasteReplyToPhone(){
 if(workspaceBusy||phonePastePending||!draftEl.value.trim()||!replyControlAvailable())return;
 window.ForegroundSync?.activity('paste');
 const card=cards.get(workspaceDevice);
 if(!card?.frame){notice('手机投屏尚未就绪，请稍后重试');return;}
 const id=crypto.randomUUID(),device=workspaceDevice,revision=workspaceRevision;
 const text=draftEl.value;
 const timer=setTimeout(()=>finishPhonePaste(id,false,'粘贴结果未确认，请先检查手机输入框，避免重复粘贴'),20000);
 const number=currentConversation?.phone_number||window.ForegroundSync?.number;
 const prepared=window.ForegroundSync?.prepareSend?.(number,text,id);
 phonePastePending={id,device,revision,text,number,prepared,frame:card.frame,origin:card.origin,timer};
 syncWorkspaceControls();notice('正在将正文粘贴到当前手机短信输入框…');
 card.frame.contentWindow.postMessage({type:'paste-composer',id,text},card.origin);
}
document.getElementById('paste-to-phone')?.addEventListener('click',pasteReplyToPhone);
function finishPhonePaste(id,ok,error){
 const pending=phonePastePending;
 if(!pending||pending.id!==id)return;
 clearTimeout(pending.timer);phonePastePending=null;
 if(pending.device===workspaceDevice&&pending.revision===workspaceRevision){
  let cleared=false;
  if(ok){
   sendBlocked=true;
   window.ForegroundSync?.expectSend(pending.number||currentConversation?.phone_number||window.ForegroundSync.number,pending.text,pending.id,pending.prepared);
   if(draftEl.value===pending.text){
    draftEl.value='';try{localStorage.removeItem(draftKey());}catch{}
    resizeDraft();cleared=true;
   }
  }
  notice(ok?(cleared?'粘贴快捷键已发出，阅读区正文已清空；请核对手机输入框后发送。':'粘贴快捷键已发出；粘贴期间新编辑的正文已保留，请核对手机输入框。'):error||'粘贴未完成，请检查手机输入框');
 }
 syncWorkspaceControls();
}
window.addEventListener('message',event=>{
 const pending=phonePastePending;
 if(!pending||event.source!==pending.frame.contentWindow||event.origin!==pending.origin||event.data?.type!=='paste-composer-result')return;
 finishPhonePaste(event.data.id,event.data.ok===true,event.data.error);
});

draftEl.addEventListener('keydown',event=>{
 if(event.key!=='Enter'||event.shiftKey||event.isComposing||event.keyCode===229)return;
 event.preventDefault();
 if(event.repeat)return;
 pasteReplyToPhone();
});
function submitReplyInput(){
 if(workspaceBusy||phonePastePending||!draftEl.value.trim()||!currentConversation)return;
 if(!replyControlAvailable())return;
 if(sendBlocked){notice('这次发送操作已处理或结果待核对；请核对手机并重新读取当前会话，禁止重复回车发送。');return;}
 const device=workspaceDevice, revision=workspaceRevision, conversation=currentConversation, text=draftEl.value;
 operation('正在核验收件人并原样发送一次…',async()=>{
  const draft=await workspaceRequest('direct_draft',{conversation_id:conversation.id,text},device);
  if(revision!==workspaceRevision||draftEl.value!==text)return;
  generatedDraft=null;sendBlocked=true;
  document.getElementById('send-reply').textContent='正在核验…';
  const result=await workspaceRequest('send',{id:draft.id,confirm:true},device);
  if(revision!==workspaceRevision)return;
  const status='正文已在手机会话中确认发送'+(result.delivered?'，已送达':'')+'。';
  draftEl.value='';try{localStorage.removeItem(draftKey());}catch{}
  showSentReply(result);
  if(!result.reading_error)notice(status);
 });
}
