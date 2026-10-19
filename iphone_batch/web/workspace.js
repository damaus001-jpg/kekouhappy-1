let workspaceDevice=null, workspaceRevision=0, savedConversations=[], currentConversation=null;
let currentConversationId=null;
let workspaceBusy=false, generatedDraft=null;
let pastedEnglish=false;
let sendBlocked=false;
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
  if(isEnglish(draftEl.value))pastedEnglish=true;
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
function notice(text){document.getElementById('archive-status').textContent=text;}
function renderConversation(){
 closeEmojiPicker();
 sendBlocked=false;
 document.getElementById('send-reply').textContent='确认发送';
 pastedEnglish=false;
 generatedDraft=null;
 document.getElementById('profile-state').textContent='待导出';document.getElementById('profile-result').replaceChildren();document.getElementById('profile-panel').open=false;
 currentConversation=savedConversations.find(c=>c.id===currentConversationId)||null;
 document.getElementById('peer-phone').textContent=currentConversation?.phone_number||'—';
 if(typeof syncContactFollowup==='function')syncContactFollowup();
 messagesEl.replaceChildren();
 draftEl.disabled=workspaceBusy;
 try{draftEl.value=currentConversation?localStorage.getItem(draftKey())||'':'';}catch{draftEl.value='';}
 const rows=currentConversation?.messages||[];
 syncWorkspaceControls();
 document.getElementById('message-count').textContent=rows.length+' 条记录';
 if(!rows.length){const empty=document.createElement('div');empty.className='message-empty';empty.textContent='尚无当前手机的已翻译记录。完成短信提取与翻译后，点击刷新记录。';messagesEl.append(empty);notice('仅显示所选手机的保存记录，不是手机当前会话的实时同步。');return;}
 for(const [index,message] of rows.entries()){
  const node=document.createElement('div');node.className='message '+(message.side==='outgoing'?'outgoing':'incoming');
  node.dataset.messageId=index;
  const meta=document.createElement('div');meta.className='message-meta';meta.textContent=(message.side==='outgoing'?'我方':message.side==='incoming'?'对方':'待核对')+' · '+(message.time||'时间未知');
  const bubble=document.createElement('div');bubble.className='bubble';
  const original=document.createElement('div');original.className='original';original.textContent=message.text||'';
  const translated=document.createElement('div');translated.className='translated';translated.textContent=message.kind==='attachment'?'图片消息 · 未翻译':message.translation_zh||'暂无译文';
  bubble.append(original,translated);node.append(meta,bubble);messagesEl.append(node);
 }
 notice('已保存记录 · '+(currentConversation.created||'时间未知')+' · 非实时同步，重复记录保留，历史完整性待核对。');
}
async function loadWorkspace(device,force=false,preferred=null){
 if(!force&&workspaceDevice===device)return;
 const requested=preferred||(workspaceDevice===device?currentConversationId:null);
 workspaceDevice=device;const revision=++workspaceRevision;savedConversations=[];currentConversation=null;currentConversationId=null;
 renderConversation();
 if(!device){notice('选择手机后加载已保存的翻译记录。');return;}
 notice('正在加载已保存的短信与译文…');
 try{const r=await fetch('/api/messages?device='+encodeURIComponent(device),{cache:'no-store'});const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'读取失败');if(revision!==workspaceRevision)return;
  savedConversations=data.conversations||[];
  currentConversationId=savedConversations.some(c=>c.id===requested)?requested:savedConversations[0]?.id||null;
  renderConversation();
 }catch(e){if(revision===workspaceRevision)notice('记录读取失败：'+e.message);}
}
document.getElementById('refresh-messages').addEventListener('click',()=>loadWorkspace(workspaceDevice,true));
draftEl.addEventListener('input',()=>{
 generatedDraft=null;if(!isEnglish(draftEl.value))pastedEnglish=false;syncWorkspaceControls();
 if(currentConversation){try{localStorage.setItem(draftKey(),draftEl.value);}catch{notice('浏览器未保存草稿。');}}
});

function syncWorkspaceControls(){
 const selected=!!workspaceDevice, available=!!currentConversation;
 for(const id of ['capture-current','refresh-messages'])document.getElementById(id).disabled=workspaceBusy||!selected;
 document.getElementById('summarize-contact').disabled=workspaceBusy||!available;
 const sendButton=document.getElementById('send-reply');
 sendButton.disabled=workspaceBusy||sendBlocked||!selected||!available||!draftEl.value.trim()||!!(generatedDraft&&!generatedDraft.sendable);
 const sendLabel=workspaceBusy?'正在处理':sendBlocked?'请先核对发送结果':isEnglish(draftEl.value)?'发送回复':'翻译为英文';
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
 const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'请求失败');return data;
}
async function operation(text, action){
 if(workspaceBusy)return;
 const sendButton=document.getElementById('send-reply');
 workspaceBusy=true;syncWorkspaceControls();notice(text);
 try{await action();}catch(e){notice(e.message);if(sendBlocked)sendButton.textContent='发送未完成';}
 finally{workspaceBusy=false;if(!sendBlocked)sendButton.textContent='确认发送';else if(sendButton.textContent==='正在核验…')sendButton.textContent='发送已处理';syncWorkspaceControls();}
}
document.getElementById('capture-current').addEventListener('click',()=>{
 const device=workspaceDevice, revision=workspaceRevision;
  operation('正在读取新增消息并核对历史；若需要数据库兜底约需两分钟，请等待…',async()=>{
  const result=await workspaceRequest('capture',{},device);if(revision!==workspaceRevision)return;
  await loadWorkspace(device,true,result.conversation_id);
  notice('已读取 '+result.contact+'；'+(result.scope||'历史范围待核对')+'。');
 });
});
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
  document.getElementById('profile-state').textContent=result.status==='filled'?'已填入':'已复制';
  const description=document.createElement('p');description.textContent=exported.message_count+' 条双方文字消息。'+message;container.append(description);
  const link=document.createElement('a');link.href='https://chatgpt.com/';link.target='_blank';link.rel='noopener noreferrer';link.textContent='打开 ChatGPT';container.append(link);
  document.getElementById('profile-panel').open=true;
 });
});
async function translateReply(){
 const device=workspaceDevice, revision=workspaceRevision, conversation=currentConversation, chinese=draftEl.value;
 if(!conversation||!chinese.trim())return;
 await operation('正在将输入框中的中文翻译为英文…',async()=>{
  const result=await workspaceRequest('draft',{conversation_id:conversation.id,chinese},device);
  if(revision!==workspaceRevision||draftEl.value!==chinese)return;
  if(!isEnglish(result.english))throw Error('翻译结果为空或仍含中文，未替换输入框，禁止发送。');
  generatedDraft=result;pastedEnglish=false;draftEl.value=result.english;
  try{localStorage.setItem(draftKey(),draftEl.value);}catch{}
  notice(result.sendable?'已转为英文，再按 Enter 直接发送。':'请先读取手机当前会话后再发送。');
  setTimeout(()=>{draftEl.focus();draftEl.setSelectionRange(draftEl.value.length,draftEl.value.length);},0);
 });
}
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
document.getElementById('send-reply').addEventListener('click',()=>{
 if(workspaceBusy||sendBlocked)return;
 const draft=generatedDraft, device=workspaceDevice, revision=workspaceRevision;
 if(!draft?.sendable){submitReplyInput();return;}
 if(!isEnglish(draftEl.value)||draftEl.value.trim()!==draft.english.trim()){
  generatedDraft=null;pastedEnglish=isEnglish(draftEl.value);submitReplyInput();return;
 }
 generatedDraft=null;sendBlocked=true;
 document.getElementById('send-reply').textContent='正在核验…';
 operation('正在核验当前收件人、会话与输入框，再发送一次…',async()=>{
  const result=await workspaceRequest('send',{id:draft.id,confirm:true},device);
  if(revision!==workspaceRevision)return;
  const text='手机会话中已确认发送'+(result.delivered?'，已送达':'；送达状态尚未确认')+'。人工回复案例已保存。';
  notice(text);
  draftEl.value='';try{localStorage.removeItem(draftKey());}catch{}
  showSentReply(result);
  if(!result.reading_error)notice(text);
 });
});

function isEnglish(text){return !!text.trim()&&!/\p{Script=Han}/u.test(text);}
draftEl.addEventListener('paste',event=>{
 pastedEnglish=isEnglish(event.clipboardData?.getData('text')||'');
});
draftEl.addEventListener('keydown',event=>{
 if(event.key!=='Enter'||event.shiftKey||event.isComposing||event.keyCode===229)return;
 event.preventDefault();
 if(event.repeat)return;
 submitReplyInput();
});
function submitReplyInput(){
 if(workspaceBusy||!draftEl.value.trim()||!currentConversation)return;
 if(!workspaceDevice){notice('预览可以输入文字和表情；连接手机后才能翻译和发送。');return;}
 if(sendBlocked){notice('这次发送操作已处理或结果待核对；请核对手机并重新读取当前会话，禁止重复回车发送。');return;}
 if(isEnglish(draftEl.value)&&!generatedDraft){
  const device=workspaceDevice, revision=workspaceRevision, conversation=currentConversation, english=draftEl.value;
  operation('正在核验收件人并发送粘贴的英文一次…',async()=>{
   const draft=await workspaceRequest('direct_draft',{conversation_id:conversation.id,english},device);
   if(revision!==workspaceRevision||draftEl.value!==english)return;
   // Leave direct-send mode before requesting a send: repeated Enter cannot retry it.
   pastedEnglish=false;generatedDraft=null;sendBlocked=true;
   document.getElementById('send-reply').textContent='正在核验…';
   const result=await workspaceRequest('send',{id:draft.id,confirm:true},device);
   if(revision!==workspaceRevision)return;
   const text='回复已在手机会话中确认发送'+(result.delivered?'，已送达':'')+'；案例已保存。';
  notice(text);
   draftEl.value='';try{localStorage.removeItem(draftKey());}catch{}
   showSentReply(result);
   if(!result.reading_error)notice(text);
  });
 }else if(generatedDraft){
  if(generatedDraft.sendable)document.getElementById('send-reply').click();
  else notice('请先读取当前完整号码会话，重新生成回复后再发送。');
 }else translateReply();
}
