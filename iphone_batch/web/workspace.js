let workspaceDevice=null, workspaceRevision=0, savedConversations=[], currentConversation=null;
let workspaceBusy=false, generatedDraft=null, unreadItems=[];
let pastedEnglish=false;
let sendBlocked=false;
let notificationItems=[];
const notificationProtection=new Map();
function protectNotificationDraft(){
 if(!workspaceDevice)return;
 const protectedDraft=!!(draftEl.value.trim()||generatedDraft||workspaceBusy);
 if(notificationProtection.get(workspaceDevice)===protectedDraft)return;
 notificationProtection.set(workspaceDevice,protectedDraft);
 fetch('/api/notification-policy',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({device:workspaceDevice,protected:protectedDraft})}).catch(()=>notificationProtection.delete(workspaceDevice));
}
function applyNotificationSnapshot(snapshot){
 if(workspaceBusy)return;
 notificationItems=snapshot.items||[];renderNotifications();
 const checked=snapshot.last_checked?new Date(snapshot.last_checked).toLocaleTimeString():'尚未检查';
 document.getElementById('notification-status').textContent=snapshot.protected?'草稿已保留，后台检查暂停':
  snapshot.state==='paused'?'检查暂停：'+snapshot.error:'全部设备自动检查 · 当前手机最近检查 '+checked;
}
const messagesEl=document.getElementById('messages'), draftEl=document.getElementById('reply-zh');
const conversationSelect=document.getElementById('conversation-select');
function draftKey(){return 'sms-draft:'+workspaceDevice+':'+(currentConversation?.contact||'');}
function notice(text){document.getElementById('archive-status').textContent=text;}
function renderConversation(){
 sendBlocked=false;
 document.getElementById('send-reply').textContent='确认发送';
 pastedEnglish=false;
 generatedDraft=null;
 document.getElementById('reply-en').value='';document.getElementById('reply-back').textContent='';
 document.getElementById('profile-state').textContent='未汇总';document.getElementById('profile-result').replaceChildren();
 currentConversation=savedConversations.find(c=>c.id===conversationSelect.value)||null;
 messagesEl.replaceChildren();
 document.getElementById('contact-title').textContent=currentConversation?.contact||'暂无已翻译会话';
 draftEl.disabled=!currentConversation;document.getElementById('copy-draft').disabled=!currentConversation;
 try{draftEl.value=currentConversation?localStorage.getItem(draftKey())||'':'';}catch{draftEl.value='';}
 document.getElementById('draft-status').textContent=draftEl.value?'已恢复中文草稿':'未填写';
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
 if(workspaceDevice!==device){unreadItems=[];notificationItems=[];renderUnread();renderNotifications();}
 workspaceDevice=device;const revision=++workspaceRevision;savedConversations=[];currentConversation=null;
 conversationSelect.replaceChildren();renderConversation();
 if(!device){document.getElementById('contact-title').textContent='尚未选择手机';notice('选择手机后加载已保存的翻译记录。');return;}
 notice('正在加载已保存的短信与译文…');
 try{const r=await fetch('/api/messages?device='+encodeURIComponent(device),{cache:'no-store'});const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'读取失败');if(revision!==workspaceRevision)return;
  savedConversations=data.conversations||[];
  for(const conversation of savedConversations){const option=document.createElement('option');option.value=conversation.id;option.textContent=conversation.contact+' · '+(conversation.created||'记录');conversationSelect.append(option);}
  if(!savedConversations.length){const option=document.createElement('option');option.textContent='暂无已翻译会话';conversationSelect.append(option);}
  if(preferred&&savedConversations.some(c=>c.id===preferred))conversationSelect.value=preferred;
  renderConversation();
 }catch(e){if(revision===workspaceRevision)notice('记录读取失败：'+e.message);}
}
conversationSelect.addEventListener('change',renderConversation);
document.getElementById('refresh-messages').addEventListener('click',()=>loadWorkspace(workspaceDevice,true));
document.getElementById('show-original').addEventListener('change',e=>messagesEl.classList.toggle('hide-original',!e.target.checked));
draftEl.addEventListener('input',()=>{generatedDraft=null;if(!isEnglish(draftEl.value))pastedEnglish=false;syncWorkspaceControls();if(!currentConversation)return;try{localStorage.setItem(draftKey(),draftEl.value);document.getElementById('draft-status').textContent=draftEl.value?(pastedEnglish?'英文草稿 · Enter 直接发送':'中文草稿 · Enter 生成英文'):'未填写';}catch{document.getElementById('draft-status').textContent='浏览器未保存草稿';}});
document.getElementById('copy-draft').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(draftEl.value);document.getElementById('draft-status').textContent='已复制中文草稿';}catch{draftEl.focus();draftEl.select();document.getElementById('draft-status').textContent='请按 Ctrl+C 复制';}});

function syncWorkspaceControls(){
 const selected=!!workspaceDevice, available=!!currentConversation;
 for(const id of ['capture-current','refresh-unread','refresh-messages','refresh-notifications'])document.getElementById(id).disabled=workspaceBusy||!selected;
 document.getElementById('summarize-contact').disabled=workspaceBusy||!available;
 document.getElementById('translate-reply').disabled=workspaceBusy||!available||!draftEl.value.trim();
 document.getElementById('send-reply').disabled=workspaceBusy||sendBlocked||!generatedDraft?.sendable;
 draftEl.disabled=workspaceBusy||!available;
 document.getElementById('copy-draft').disabled=workspaceBusy||!available;
 conversationSelect.disabled=workspaceBusy;
 document.querySelectorAll('#unread-list .unread-chip').forEach((button,i)=>button.disabled=workspaceBusy||!unreadItems[i]?.clickable);
 document.querySelectorAll('.notification-chip').forEach((button,i)=>button.disabled=workspaceBusy||!notificationItems[i]?.clickable);
 protectNotificationDraft();
}
function renderNotifications(){
 const list=document.getElementById('notification-list');list.replaceChildren();
 document.getElementById('notification-count').textContent=notificationItems.length?'· '+notificationItems.length+' 个':'';
 if(!notificationItems.length){const hint=document.createElement('span');hint.className='muted';hint.textContent='暂未发现待处理的 Messages 通知；其他 App 通知跳过。';list.append(hint);return;}
 for(const item of notificationItems){
  const button=document.createElement('button');button.type='button';button.className='unread-chip notification-chip';
  button.disabled=workspaceBusy||!item.clickable;
  button.title=item.clickable?'打开短信通知并核验收件人':'通知仅显示姓名，完整号码待核对';
  const name=document.createElement('strong');name.textContent=item.sender+(item.grouped?' · 分组':'');
  const preview=document.createElement('span');preview.textContent=item.preview;
  button.append(name,preview);button.addEventListener('click',()=>openNotification(item));list.append(button);
 }
}
async function checkNotifications(background=false){
 if(workspaceBusy||!workspaceDevice)return;
 const status=document.getElementById('notification-status');
 if(draftEl.value.trim()||generatedDraft){status.textContent='回复草稿已保留，通知检查暂停；处理草稿后继续。';return;}
 const device=workspaceDevice, revision=workspaceRevision;
 workspaceBusy=true;syncWorkspaceControls();
 if(!background)status.textContent='正在检查通知中心，随后返回原页面…';
 try{
  const result=await workspaceRequest('notifications',{},device);
  if(revision!==workspaceRevision)return;
  notificationItems=result.items||[];renderNotifications();
  status.textContent='最近检查 '+new Date().toLocaleTimeString()+' · '+notificationItems.length+' 个待处理短信通知 · 其他 App 已跳过';
 }catch(error){if(revision===workspaceRevision)status.textContent='通知检查暂停：'+error.message;}
 finally{workspaceBusy=false;syncWorkspaceControls();}
}
async function openNotification(item){
 if(draftEl.value.trim()||generatedDraft){notice('回复草稿已保留，请先处理草稿再打开其他会话。');return;}
 const device=workspaceDevice, revision=workspaceRevision;
 await operation('正在打开短信通知，核验号码并读取新消息…',async()=>{
  const result=await workspaceRequest('open_notification',{notification_id:item.id},device);
  if(revision!==workspaceRevision)return;
  notificationItems=notificationItems.filter(row=>row.id!==item.id);
  await loadWorkspace(device,true,result.conversation_id);renderNotifications();
  notice('已从短信通知进入 '+result.contact+'，收件人已核验；'+result.scope);
 });
}
document.getElementById('refresh-notifications').addEventListener('click',()=>checkNotifications());
document.getElementById('watch-notifications').addEventListener('change',event=>{if(event.target.checked)checkNotifications();});
// All-device checks are scheduled by the backend, including when this tab is hidden.
async function workspaceRequest(action, extra={}, device=workspaceDevice){
 const r=await fetch('/api/workspace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,device,...extra})});
 const data=await r.json();if(!r.ok||data.error)throw Error(data.error||'请求失败');return data;
}
async function operation(text, action){
 if(workspaceBusy)return;
 const sendButton=document.getElementById('send-reply');
 workspaceBusy=true;syncWorkspaceControls();notice(text);
 if(sendButton.textContent==='正在核验…')document.getElementById('send-status').textContent=text;
 try{await action();}catch(e){notice(e.message);document.getElementById('send-status').textContent=e.message;if(sendBlocked)sendButton.textContent='发送未完成';}
 finally{workspaceBusy=false;if(!sendBlocked)sendButton.textContent='确认发送';else if(sendButton.textContent==='正在核验…')sendButton.textContent='发送已处理';syncWorkspaceControls();}
}
function renderUnread(){
 const list=document.getElementById('unread-list');list.replaceChildren();
 document.getElementById('unread-count').textContent=unreadItems.length?'· '+unreadItems.length+' 个':'';
 if(!unreadItems.length){const hint=document.createElement('span');hint.className='muted';hint.textContent='点击刷新未读，识别所选手机的会话。';list.append(hint);return;}
 unreadItems.forEach(item=>{
  const button=document.createElement('button');button.type='button';button.className='unread-chip'+(item.phone_number===currentConversation?.phone_number?' current':'');button.disabled=!item.clickable||workspaceBusy;
  button.title=item.clickable?'打开并翻译这个未读会话':'联系人仅显示姓名，需用完整号码命名后才能准确打开';
  const name=document.createElement('strong');name.textContent=item.name;const preview=document.createElement('span');preview.textContent=item.preview;button.append(name,preview);
  button.addEventListener('click',()=>openUnread(item));list.append(button);
 });
}
async function openUnread(item){
 const device=workspaceDevice, revision=workspaceRevision;
 await operation('正在按完整号码打开未读会话，并读取、翻译短信…',async()=>{
  generatedDraft=null;const result=await workspaceRequest('open',{phone_number:item.phone_number},device);
  if(revision!==workspaceRevision)return;
  unreadItems=unreadItems.filter(i=>i.phone_number!==item.phone_number);
  await loadWorkspace(device,true,result.conversation_id);renderUnread();
  notice('已打开 '+result.contact+'，下方显示本次读取的短信与译文。');
 });
}
document.getElementById('refresh-unread').addEventListener('click',()=>{
 const device=workspaceDevice, revision=workspaceRevision;
 operation('正在读取未读列表；手机无草稿时返回短信列表…',async()=>{
  generatedDraft=null;const result=await workspaceRequest('unread',{},device);
  if(revision!==workspaceRevision)return;
  unreadItems=result.items||[];renderUnread();
  document.getElementById('unread-status').textContent=result.scope+(unreadItems.some(i=>!i.clickable)?'；仅显示姓名的联系人需按完整号码命名。':'');
  notice(unreadItems.length?'未读列表已更新，点击号码进入会话。':result.complete?'当前列表没有未读会话。':'本次发现 0 个未读，遍历尚未完整，请再次刷新。');
 });
});
document.getElementById('capture-current').addEventListener('click',()=>{
 const device=workspaceDevice, revision=workspaceRevision;
  operation('正在读取新增消息并核对历史；若需要数据库兜底约需两分钟，请等待…',async()=>{
  const result=await workspaceRequest('capture',{},device);if(revision!==workspaceRevision)return;
  await loadWorkspace(device,true,result.conversation_id);renderUnread();
  notice('已读取 '+result.contact+'；'+(result.scope||'历史范围待核对')+'。');
 });
});
document.getElementById('summarize-contact').addEventListener('click',()=>{
 const device=workspaceDevice, revision=workspaceRevision, conversation=currentConversation;
 if(!conversation)return;
 operation('正在汇总对方资料并核验原文依据…',async()=>{
  const result=await workspaceRequest('profile',{conversation_id:conversation.id},device);if(revision!==workspaceRevision)return;
  const container=document.getElementById('profile-result');container.replaceChildren();
  document.getElementById('profile-state').textContent=result.fields.length+' 项';
  if(!result.fields.length){const p=document.createElement('p');p.textContent='已提取消息中没有可核验的对方资料。';container.append(p);}
  for(const field of result.fields){
   const row=document.createElement('div');row.className='profile-field';const label=document.createElement('strong');label.textContent=field.label+(field.needs_review?' · 存在不同表述，请核对':'');
   const value=document.createElement('div');value.textContent=field.value;const evidence=document.createElement('details');evidence.className='profile-evidence';const summary=document.createElement('summary');summary.textContent='查看原文依据';evidence.append(summary);
   for(const item of field.evidence){const source=document.createElement('pre');source.textContent=(item.time||'')+' · '+item.text+(item.translation_zh?'\n中文：'+item.translation_zh:'');const jump=document.createElement('button');jump.type='button';jump.className='secondary';jump.textContent='定位这条短信';jump.onclick=()=>{const node=messagesEl.querySelector('[data-message-id="'+item.id+'"]');if(node){document.getElementById('profile-panel').open=false;node.scrollIntoView({block:'center',behavior:'smooth'});node.classList.add('highlight');setTimeout(()=>node.classList.remove('highlight'),2000);}};evidence.append(source,jump);}
   row.append(label,value,evidence);container.append(row);
  }
  document.getElementById('profile-panel').open=true;notice(result.scope+(result.cached?' · 已复用汇总结果':''));
 });
});
document.getElementById('translate-reply').addEventListener('click',()=>{
 const device=workspaceDevice, revision=workspaceRevision, conversation=currentConversation, chinese=draftEl.value;
 if(!conversation||!chinese.trim())return;
 operation('正在将中文回复翻译为英文，并生成中文回译…',async()=>{
  const result=await workspaceRequest('draft',{conversation_id:conversation.id,chinese},device);
  if(revision!==workspaceRevision||draftEl.value!==chinese)return;
  generatedDraft=result;document.getElementById('reply-en').value=result.english;document.getElementById('reply-back').textContent='中文回译：'+result.back_translation_zh;
  document.getElementById('reply-preview').open=true;document.getElementById('reply-box').open=true;
  document.getElementById('draft-status').textContent='英文已生成，尚未发送';
  document.getElementById('send-status').textContent=result.sendable?'收件人：'+result.phone_number+'。确认英文与回译后点击发送。':'当前是历史记录或未核验完整号码；请读取号码会话后重新生成回复。';
  notice('英文与中文回译已生成；这次人工回复已保存为草稿案例。');
 });
});
function showSentReply(result){
 if(result.conversation){
  const conversation=result.conversation;
  savedConversations=savedConversations.filter(c=>c.id!==conversation.id);
  savedConversations.unshift(conversation);
  let option=Array.from(conversationSelect.options).find(o=>o.value===conversation.id);
  if(!option){option=document.createElement('option');option.value=conversation.id;conversationSelect.prepend(option);}
  option.textContent=conversation.contact+' · '+(conversation.created||'记录');
  conversationSelect.value=conversation.id;
  renderConversation();renderUnread();
  document.getElementById('draft-status').textContent='已发送，案例已保存';
  messagesEl.lastElementChild?.scrollIntoView({block:'end',behavior:'smooth'});
 }
 if(result.reading_error)notice('发送已确认；阅读区更新失败：'+result.reading_error+'。请读取当前会话，勿重复发送。');
}
document.getElementById('send-reply').addEventListener('click',()=>{
 const draft=generatedDraft, device=workspaceDevice, revision=workspaceRevision;if(!draft?.sendable)return;
 generatedDraft=null;sendBlocked=true;
 document.getElementById('send-reply').textContent='正在核验…';
 operation('正在核验当前收件人、会话与输入框，再发送一次…',async()=>{
  const result=await workspaceRequest('send',{id:draft.id,confirm:true},device);
  if(revision!==workspaceRevision)return;
  const text='手机会话中已确认发送'+(result.delivered?'，已送达':'；送达状态尚未确认')+'。人工回复案例已保存。';
  notice(text);document.getElementById('send-status').textContent=text;document.getElementById('draft-status').textContent='已发送，案例已保存';
  draftEl.value='';try{localStorage.removeItem(draftKey());}catch{}
  showSentReply(result);
  if(!result.reading_error)notice(text);
 });
});

function isEnglish(text){return !!text.trim()&&!/\p{Script=Han}/u.test(text);}
draftEl.addEventListener('paste',event=>{
 pastedEnglish=isEnglish(event.clipboardData?.getData('text')||'');
 setTimeout(()=>{if(pastedEnglish&&isEnglish(draftEl.value))document.getElementById('draft-status').textContent='已粘贴英文 · Enter 直接发送';},0);
});
draftEl.addEventListener('keydown',event=>{
 if(event.key!=='Enter'||event.shiftKey||event.isComposing||event.keyCode===229)return;
 event.preventDefault();
 if(workspaceBusy||!draftEl.value.trim()||!currentConversation)return;
 if(sendBlocked){notice('这次发送操作已处理或结果待核对；请核对手机并重新读取当前会话，禁止重复回车发送。');return;}
 if(pastedEnglish&&isEnglish(draftEl.value)){
  const device=workspaceDevice, revision=workspaceRevision, conversation=currentConversation, english=draftEl.value;
  operation('正在核验收件人并发送粘贴的英文一次…',async()=>{
   const draft=await workspaceRequest('direct_draft',{conversation_id:conversation.id,english},device);
   if(revision!==workspaceRevision||draftEl.value!==english)return;
   // Leave direct-send mode before requesting a send: repeated Enter cannot retry it.
   pastedEnglish=false;generatedDraft=null;sendBlocked=true;
   document.getElementById('send-reply').textContent='正在核验…';document.getElementById('send-status').textContent='正在核验收件人并发送一次…';
   const result=await workspaceRequest('send',{id:draft.id,confirm:true},device);
   if(revision!==workspaceRevision)return;
   const text='回复已在手机会话中确认发送'+(result.delivered?'，已送达':'')+'；案例已保存。';
   notice(text);document.getElementById('send-status').textContent=text;document.getElementById('draft-status').textContent='已发送';
   draftEl.value='';try{localStorage.removeItem(draftKey());}catch{}
   showSentReply(result);
   if(!result.reading_error)notice(text);
  });
 }else if(generatedDraft){
  if(generatedDraft.sendable)document.getElementById('send-reply').click();
  else notice('请先读取当前完整号码会话，重新生成回复后再发送。');
 }else document.getElementById('translate-reply').click();
});
