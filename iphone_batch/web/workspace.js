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
function draftKey(){const device=workspaceDevice||(typeof devicePreview!=='undefined'&&devicePreview?'preview:'+active:'');return 'sms-draft:'+device+':'+(currentConversation?.contact||'');}
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
 document.getElementById('archive-status').textContent=text;
 const monitorNotice=document.getElementById('monitor-notice');
 const passive=/^(仅显示所选手机的保存记录|选择手机后加载|正在加载已保存|已保存记录)/.test(text)||text===currentConversation?.scope;
 if(monitorNotice&&(!passive||!monitorNotice.dataset.operation)){
  monitorNotice.textContent=text;
  if(/^设备\s/.test(text))monitorNotice.dataset.operation='true';
 }
}
function renderConversation(){
 closeEmojiPicker();
 sendBlocked=false;
 document.getElementById('send-reply').textContent='确认发送';
 pastedEnglish=false;
 generatedDraft=null;
 document.getElementById('profile-result').replaceChildren();document.getElementById('profile-panel').open=false;
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
 for(const [index,message] of rows.entries()){
  const node=document.createElement('div');node.className='message '+(message.side==='outgoing'?'outgoing':'incoming');
  node.dataset.messageId=index;
  const meta=document.createElement('div');meta.className='message-meta';meta.textContent=(message.side==='outgoing'?'我方':message.side==='incoming'?'对方':'待核对')+' · '+(message.time||'时间未知');
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
 generatedDraft=null;syncWorkspaceControls();
 if(currentConversation){try{localStorage.setItem(draftKey(),draftEl.value);}catch{notice('浏览器未保存草稿。');}}
});

function syncWorkspaceControls(){
 if(typeof syncDeviceRefreshControls==='function')syncDeviceRefreshControls();
 if(typeof sendFocus==='function')for(const card of cards.values()){
  if(card.lastWorking!==workspaceBusy){sendFocus(card,card.lastActive===true);card.lastWorking=workspaceBusy;}
 }
 const selected=!!workspaceDevice&&(typeof controlOwner==='undefined'||controlOwner===workspaceDevice), available=!!currentConversation;
 for(const id of ['capture-current','sync-full-history','refresh-messages'])document.getElementById(id).disabled=workspaceBusy||!selected;
 document.getElementById('summarize-contact').disabled=workspaceBusy||!available;
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
 operation(full?'正在同步手机短信数据库，可能需要较长时间…':'正在读取手机屏幕当前可见的气泡…',async()=>{
  const result=await workspaceRequest('capture',full?{full:true}:{},device);if(revision!==workspaceRevision)return;
  await loadWorkspace(device,true,result.conversation_id);
  notice('已读取 '+result.contact+'；'+(result.scope||'历史范围待核对')+'。');
 });
}
document.getElementById('capture-current').addEventListener('click',()=>captureConversation(false));
document.getElementById('sync-full-history').addEventListener('click',()=>captureConversation(true));
document.getElementById('summarize-contact').addEventListener('click',()=>{
 const conversation=currentConversation;
 if(!conversation)return;
 operation('正在整理双方文字、复制到剪贴板并打开 ChatGPT…',async()=>{
  const exported=buildGptProfileExport(conversation);
  const response=await fetch('/api/gpt-summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:exported.text})});
  const result=await response.json();if(!response.ok||result.error)throw Error(result.error||'打开 ChatGPT 失败');
  const messages={filled:'已复制并填入 ChatGPT 输入框，请检查后自行发送。',
   existing_draft:'已复制。ChatGPT 输入框已有草稿，已保留原内容；请自行粘贴。',
   page_not_ready:'已复制并打开浏览器。请完成 ChatGPT 登录或等待页面加载，再点击去汇总；也可自行粘贴。',
   unverified:'已复制，输入框填入结果尚未确认，请检查 ChatGPT 页面，避免重复粘贴。',
   browser_error:'文字已复制，自动填入未完成；请打开 ChatGPT 后粘贴。',
   browser_unavailable:'文字已复制，未找到可用浏览器；请打开 ChatGPT 后粘贴。'};
  const message=messages[result.status]||'文字已复制，请在 ChatGPT 查看。';
  notice(message);
  if(currentConversation?.id!==conversation.id)return;
  const container=document.getElementById('profile-result');container.replaceChildren();
  const description=document.createElement('p');description.textContent=exported.message_count+' 条双方文字消息。'+message+' 汇总后复制 GPT 的 JSON 结果，粘贴到下方并填入资料。';container.append(description);
  const link=document.createElement('a');link.href='https://chatgpt.com/';link.target='_blank';link.rel='noopener noreferrer';link.textContent='打开 ChatGPT';container.append(link);
  document.getElementById('profile-panel').open=true;
 });
});
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
document.getElementById('paste-to-phone')?.addEventListener('click',()=>{
 if(workspaceBusy||phonePastePending||!draftEl.value.trim()||!replyControlAvailable())return;
 const card=cards.get(workspaceDevice);
 if(!card?.frame){notice('手机投屏尚未就绪，请稍后重试');return;}
 const id=crypto.randomUUID(),device=workspaceDevice,revision=workspaceRevision;
 const text=draftEl.value;
 const timer=setTimeout(()=>finishPhonePaste(id,false,'粘贴结果未确认，请先检查手机输入框，避免重复粘贴'),20000);
 phonePastePending={id,device,revision,frame:card.frame,origin:card.origin,timer};
 syncWorkspaceControls();notice('正在将正文粘贴到当前手机短信输入框…');
 card.frame.contentWindow.postMessage({type:'paste-composer',id,text},card.origin);
});
function finishPhonePaste(id,ok,error){
 const pending=phonePastePending;
 if(!pending||pending.id!==id)return;
 clearTimeout(pending.timer);phonePastePending=null;
 if(pending.device===workspaceDevice&&pending.revision===workspaceRevision){
  if(ok)sendBlocked=true;
  notice(ok?'已请求粘贴正文，请核对手机会话和内容后，点击手机发送按钮。阅读区正文已保留。':error||'粘贴未完成，请检查手机输入框');
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
 submitReplyInput();
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
