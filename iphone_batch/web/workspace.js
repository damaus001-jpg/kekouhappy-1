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
  body:JSON.stringify({device:workspaceDevice,protected:protectedDraft})}).catch(()=>notificationProtection.delete(workspaceDevice));
}
const messagesEl=document.getElementById('messages'), draftEl=document.getElementById('reply-zh');
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
function renderConversation(){
 closeEmojiPicker();
 sendBlocked=false;
 document.getElementById('send-reply').textContent='确认发送';
 pastedEnglish=false;
 generatedDraft=null;
 currentConversation=savedConversations.find(c=>c.id===currentConversationId)||null;
 if(typeof refreshContactProfile==='function')refreshContactProfile();
 document.getElementById('peer-phone').textContent=currentConversation?.phone_number||'—';
 if(typeof syncContactFollowup==='function')syncContactFollowup();
 messagesEl.replaceChildren();
 draftEl.disabled=workspaceBusy;
 try{draftEl.value=currentConversation?localStorage.getItem(draftKey())||'':'';}catch{draftEl.value='';}
 const rows=currentConversation?.messages||[];
 syncWorkspaceControls();
 document.getElementById('message-count').textContent=rows.length+' 条记录';
 if(!rows.length){const empty=document.createElement('div');empty.className='message-empty';empty.textContent='尚无当前手机的保存记录。读取当前会话后显示短信原文。';messagesEl.append(empty);notice('仅显示所选手机的保存记录，不是手机当前会话的实时同步。');return;}
 const peerNumber=String(currentConversation?.phone_number||currentConversation?.contact||'').trim();
 let previousDate='';
 for(const [index,message] of rows.entries()){
  // Backup timestamps already carry an offset. Preserve their recorded day
  // and timezone even when the workstation is in a different timezone.
  const iso=typeof message.time==='string'&&message.time.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/);
  const date=readingDateLabel(message)||(iso?iso[1]+'年'+Number(iso[2])+'月'+Number(iso[3])+'日':'');
  const time=iso?iso[4]+' UTC'+(['Z','+00:00'].includes(iso[5])?'':iso[5]):message.time;
  if(date!==previousDate){
   const separator=document.createElement('div');separator.className='message-date';separator.textContent=date||'日期待确认';
   messagesEl.append(separator);
  }
  previousDate=date;
  const node=document.createElement('div');node.className='message '+(message.side==='outgoing'?'outgoing':'incoming');
  node.dataset.messageId=index;
  const meta=document.createElement('div');meta.className='message-meta';meta.textContent=(message.side==='outgoing'?'我方':message.side==='incoming'?'对方':'待核对')+' · '+(time||'时间未知')+(message.side==='incoming'&&peerNumber?' · '+peerNumber:'');
  const bubble=document.createElement('div');bubble.className='bubble';
  const original=document.createElement('div');original.className='original';original.textContent=message.text||(message.kind==='attachment'?'[附件消息]':message.decode_error?'[正文解析未完成]':'[无文字内容]');
  bubble.append(original);node.append(meta,bubble);messagesEl.append(node);
 }
 notice(currentConversation.scope||('已保存记录 · '+(currentConversation.created||'时间未知')+' · 非实时同步，重复记录保留，历史完整性待核对。'));
}
async function loadWorkspace(device,force=false,preferred=null){
 if(!force&&workspaceDevice===device)return;
 const requested=preferred||(workspaceDevice===device?currentConversationId:null);
 workspaceDevice=device;const revision=++workspaceRevision;savedConversations=[];currentConversation=null;currentConversationId=null;
 renderConversation();
 if(!device){notice('选择手机后加载已保存的短信原文。');return;}
 notice('正在加载已保存的短信原文…');
 try{const r=await fetch('/api/messages?device='+encodeURIComponent(device),{cache:'no-store'});const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'读取失败');if(revision!==workspaceRevision)return;
  savedConversations=data.conversations||[];
  currentConversationId=savedConversations.some(c=>c.id===requested)?requested:savedConversations[0]?.id||null;
  renderConversation();
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
 const selected=!!workspaceDevice&&(typeof controlOwner==='undefined'||controlOwner===workspaceDevice), available=!!currentConversation;
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
  const result=await workspaceRequest('capture',full?{full:true}:{},device);if(revision!==workspaceRevision)return;
  await loadWorkspace(device,true,result.conversation_id);
  notice('已读取 '+result.contact+'；'+(result.scope||'历史范围待核对')+'。');
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
  messagesEl.lastElementChild?.scrollIntoView({block:'end',behavior:'smooth'});
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
 phonePastePending={id,device,revision,text,frame:card.frame,origin:card.origin,timer};
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
   window.ForegroundSync?.expectSend(currentConversation?.phone_number||window.ForegroundSync.number,pending.text);
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
