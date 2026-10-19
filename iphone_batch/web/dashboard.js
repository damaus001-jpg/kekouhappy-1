
const cards=new Map();let active=null;let busy=false;let latest=[];let controlPaused=false;
const devicePreview=location.hash==='#preview-devices';
let previewSelection=null;
const previewDevices=Array.from({length:20},(_,i)=>({
 udid:'preview-device-'+(i+1),number:String(i+1).padStart(2,'0'),name:'iPhone '+(i+1),
 followup:[2,5,10,13].includes(i),
 ready:false,port:8080+i,
 notifications:{card_count:[3,0,12,1,0,6,0,2,0,0,5,0,8,0,1,0,0,4,0,99][i],last_checked:'2026-10-18T12:00:00Z'}
}));
let editingDevice=null;
let previewLoadedDevice=null;
const sortControl=document.getElementById('device-sort');
const followupControl=document.getElementById('device-followup');
const sortStorageKey='iphone-device-sort:'+(devicePreview?'preview':'device');
try{sortControl.value=localStorage.getItem(sortStorageKey)==='unread'?'unread':'followup';}catch{}
sortControl.addEventListener('change',()=>{
 try{localStorage.setItem(sortStorageKey,sortControl.value);}catch{}
 render(latest,active);
});
let deviceMenuTarget=null;
const deviceMenu=document.getElementById('device-context-menu');
function closeDeviceMenu(){deviceMenu.hidden=true;deviceMenuTarget=null;}
function showDeviceMenu(event,device,index){
 event.preventDefault();deviceMenuTarget={device,index};deviceMenu.hidden=false;
 const followup=deviceLabel(device,index).followup;
 document.getElementById('device-context-followup').setAttribute('aria-checked',String(followup));
 document.getElementById('device-context-none').setAttribute('aria-checked',String(!followup));
 const bounds=deviceMenu.getBoundingClientRect();
 deviceMenu.style.left=Math.max(4,Math.min(event.clientX,window.innerWidth-bounds.width-4))+'px';
 deviceMenu.style.top=Math.max(4,Math.min(event.clientY,window.innerHeight-bounds.height-4))+'px';
 document.getElementById('device-context-edit').focus();
}
document.getElementById('device-context-edit').addEventListener('click',()=>{
 const target=deviceMenuTarget;closeDeviceMenu();if(target)editDevice(target.device,target.index);
});
for(const [id,followup] of [['device-context-followup',true],['device-context-none',false]]){
 document.getElementById(id).addEventListener('click',()=>{
  const target=deviceMenuTarget;closeDeviceMenu();if(target)setDeviceFollowup(target.device,followup);
 });
}
followupControl.addEventListener('change',()=>{
 const context=contactFollowupContext();
 if(!context)return;
 const records=contactFollowups(context.device);
 if(followupControl.checked)records[context.key]={followup:true,contact:currentConversation.contact,
  phone_number:context.key.startsWith('phone:')?'+'+context.key.slice(6):null};else delete records[context.key];
 try{localStorage.setItem(contactFollowupStorageKey(context.device),JSON.stringify(records));}
 catch{notice('保存失败，请允许此页面使用本地存储后重试。');syncContactFollowup();return;}
 render(latest,active);
});
document.addEventListener('pointerdown',event=>{if(!deviceMenu.contains(event.target))closeDeviceMenu();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeDeviceMenu();});
document.addEventListener('scroll',closeDeviceMenu,true);
window.addEventListener('resize',closeDeviceMenu);
const readingPopups=new Map();
function positionReadingCards(){
 for(const [id,selector,width] of [['followup-panel','.followup-contact-list',368],['profile-panel','.profile-body',380]]){
  const panel=document.getElementById(id);
  const popup=readingPopups.get(id)||panel.querySelector(selector);if(!popup)continue;
  if(!panel.open){if(readingPopups.has(id)){panel.append(popup);popup.classList.remove('reading-floating-card');readingPopups.delete(id);}continue;}
  if(!readingPopups.has(id)){popup.classList.add('reading-floating-card');document.body.append(popup);readingPopups.set(id,popup);}
  const bounds=panel.getBoundingClientRect();
  const popupWidth=Math.min(width,window.innerWidth-24);
  const top=Math.min(bounds.bottom+6,window.innerHeight-100);
  popup.style.width=popupWidth+'px';
  popup.style.left=Math.max(12,Math.min(bounds.right-popupWidth,window.innerWidth-popupWidth-12))+'px';
  popup.style.top=Math.max(12,top)+'px';
  popup.style.maxHeight=Math.max(80,window.innerHeight-top-12)+'px';
 }
}
for(const id of ['followup-panel','profile-panel'])document.getElementById(id).addEventListener('toggle',positionReadingCards);
window.addEventListener('resize',positionReadingCards);
document.addEventListener('scroll',positionReadingCards,true);
function deviceLabelKey(device){return 'iphone-device-label:'+(devicePreview?'preview:':'device:')+device.udid;}
function contactFollowupStorageKey(device){return 'iphone-contact-followups:'+(devicePreview?'preview:':'device:')+device.udid;}
function contactFollowups(device){
 try{
  const saved=JSON.parse(localStorage.getItem(contactFollowupStorageKey(device))||'{}');
  return saved&&typeof saved==='object'&&!Array.isArray(saved)?saved:{};
 }catch{return {};}
}
function isContactFollowup(value){return value===true||value?.followup===true;}
function contactFollowupCount(device){return Object.values(contactFollowups(device)).filter(isContactFollowup).length;}
function contactFollowupContext(){
 const device=latest.find(row=>row.udid===active);
 if(!device||typeof currentConversation==='undefined'||!currentConversation)return null;
 if((devicePreview?previewLoadedDevice:workspaceDevice)!==device.udid)return null;
 const contact=String(currentConversation.phone_number||currentConversation.contact||'').trim();
 if(!contact)return null;
 const digits=contact.replace(/\D/g,'');
 const key=/^\+?[\d\s().-]+$/.test(contact)&&digits.length>=7?'phone:'+digits:'contact:'+contact;
 return {device,key};
}
function syncContactFollowup(){
 const context=contactFollowupContext();
 followupControl.disabled=!context;
 followupControl.checked=!!(context&&isContactFollowup(contactFollowups(context.device)[context.key]));
 followupControl.title=context?'标记当前联系人，同一手机的同一联系人只计一次':'先读取联系人会话';
 renderFollowupContacts();
}
function renderFollowupContacts(){
 const list=document.getElementById('followup-contact-list');list.replaceChildren();
 const device=latest.find(row=>row.udid===active);
 const records=device?Object.entries(contactFollowups(device)).filter(([,value])=>isContactFollowup(value)):[];
 document.getElementById('followup-contact-count').textContent=String(records.length);
 if(!records.length){const hint=document.createElement('span');hint.className='muted';hint.textContent='在阅读区勾选联系人后显示在这里。';list.append(hint);return;}
 for(const [key,value] of records){
  const number=key.startsWith('phone:')?'+'+key.slice(6):null;
  const button=document.createElement('button');button.type='button';button.className='followup-contact';
  button.disabled=workspaceBusy||!number;
  button.textContent=(value?.contact||number||key.slice(8))+(number&&value?.contact&&value.contact!==number?' · '+number:'');
  button.title=number?'在手机打开 '+number+' 并读取会话':'没有完整号码，请先手动进入会话读取';
  button.onclick=()=>openFollowupContact(device.udid,number);list.append(button);
 }
}
async function openFollowupContact(device,number){
 if(workspaceBusy||busy||!number||active!==device)return;
 if(draftEl.value.trim()||generatedDraft){notice('回复草稿已保留，请先处理草稿再打开其他会话。');return;}
 if(devicePreview){
  const conversation=savedConversations.find(row=>String(row.phone_number||'').replace(/\D/g,'')===number.slice(1));
  if(conversation){currentConversationId=conversation.id;renderConversation();render(latest,active);}
  notice('预览：已选择 '+number+'；真实设备会输入此号码打开会话。');return;
 }
 const revision=workspaceRevision;
 await operation('正在手机打开 '+number+'，核验号码并读取短信…',async()=>{
  const result=await workspaceRequest('open',{phone_number:number},device);
  if(revision!==workspaceRevision||active!==device)return;
  if(result.phone_number!==number)throw Error('打开后的号码不一致，请核对手机。');
  await loadWorkspace(device,true,result.conversation_id);
  notice('手机已打开 '+number+'；'+(result.scope||'已读取会话并翻译'));
 });
}
async function showDeviceFollowups(device){
 if(workspaceBusy||busy)return;
 if(draftEl.value.trim()||generatedDraft){notice('回复草稿已保留，请先处理草稿再切换。');return;}
 if(active!==device)await select(device);
 if(active===device){document.getElementById('followup-panel').open=true;renderFollowupContacts();}
}
function loadPreviewContacts(device){
 if(typeof savedConversations==='undefined'||previewLoadedDevice===device?.udid)return;
 previewLoadedDevice=device?.udid||null;
 savedConversations=device?Array.from({length:3},(_,index)=>({
  id:device.udid+'-contact-'+index,contact:'预览联系人 '+(index+1),phone_number:'+15550000'+String(index+1).padStart(3,'0'),
  messages:[{side:'incoming',time:'12:00',kind:'text',text:'Hello, can we talk later?',translation_zh:'你好，我们可以晚点聊吗？'}]
 })):[];
 currentConversationId=savedConversations[0]?.id||null;
 renderConversation();
}
function deviceLabel(device,index){
 let saved=null;
 try{saved=JSON.parse(localStorage.getItem(deviceLabelKey(device))||'null');}catch{}
 return {number:typeof saved?.number==='string'&&saved.number.trim()?saved.number:device.number||String(index+1).padStart(2,'0'),
  followup:typeof saved?.followup==='boolean'?saved.followup:saved?.remark==='待跟进'||device.followup===true};
}
function setDeviceFollowup(device,followup){
 const label=deviceLabel(device,latest.indexOf(device));
 try{localStorage.setItem(deviceLabelKey(device),JSON.stringify({...label,followup}));}
 catch{notice('保存失败，请允许此页面使用本地存储后重试。');return;}
 render(latest,active);
}
function editDevice(device,index){
 const label=deviceLabel(device,index);editingDevice=device;
 document.getElementById('device-number-input').value=label.number;
 document.getElementById('device-label-error').textContent='';
 document.getElementById('device-label-dialog').showModal();
 document.getElementById('device-number-input').focus();
}
document.getElementById('device-label-cancel').addEventListener('click',()=>document.getElementById('device-label-dialog').close());
document.getElementById('device-label-form').addEventListener('submit',event=>{
 event.preventDefault();if(!editingDevice)return;
 const number=document.getElementById('device-number-input').value.trim();
 const error=document.getElementById('device-label-error');
 if(!number||number.length>16){error.textContent='编号必填，最多 16 字。';return;}
 const label=deviceLabel(editingDevice,latest.indexOf(editingDevice));
 try{localStorage.setItem(deviceLabelKey(editingDevice),JSON.stringify({...label,number}));}
 catch{error.textContent='保存失败，请允许此页面使用本地存储后重试。';return;}
 document.getElementById('device-label-dialog').close();editingDevice=null;
 render(latest,active);
});
function sendFocus(card,on){if(card.frame) card.frame.contentWindow.postMessage({type:'device-focus',active:on},card.origin);}
function render(rows,selected){
 latest=rows;active=selected;
 controlPaused=rows.some(row=>row.udid===selected&&row.notifications?.state==='scanning');
 const selectedDevice=rows.find(device=>device.udid===selected);
 const readingDeviceLabel=selectedDevice?deviceLabel(selectedDevice,rows.indexOf(selectedDevice)):null;
 document.getElementById('reading-device-number').textContent='设备：'+(readingDeviceLabel?.number||'—');
 if(devicePreview)loadPreviewContacts(selectedDevice);else loadWorkspace(selected);
 syncContactFollowup();
 document.getElementById('device-count').textContent=rows.length+' 台';
 const deviceList=document.getElementById('device-list');deviceList.replaceChildren();
 const ordered=rows.map((device,index)=>({device,index,label:deviceLabel(device,index),followupCount:contactFollowupCount(device)}));
 ordered.sort((a,b)=>sortControl.value==='unread'?
  ((b.device.notifications?.card_count??b.device.notifications?.items?.length??0)-(a.device.notifications?.card_count??a.device.notifications?.items?.length??0)||a.index-b.index):
  (b.followupCount-a.followupCount||a.index-b.index));
 for(const {device:d,index,label,followupCount} of ordered){
  const entry=document.createElement('button');entry.type='button';entry.className='device-entry'+(selected===d.udid?' current':'');entry.disabled=(!devicePreview&&!d.ready)||busy;entry.setAttribute('aria-pressed',String(selected===d.udid));
  const number=label.number;
  const name=document.createElement('strong');name.textContent='设备 '+number;
  const remark=document.createElement('span');remark.className='device-remark'+(followupCount||label.followup?' followup':'');remark.textContent=followupCount||label.followup?'待跟进 '+followupCount:'无';
  remark.title='阅读区已勾选 '+followupCount+' 位联系人';
  remark.addEventListener('click',event=>{event.stopPropagation();showDeviceFollowups(d.udid);});
  const detail=document.createElement('span');detail.className='device-state';
  const phone=document.createElement('span');phone.className='device-phone';phone.setAttribute('aria-hidden','true');
  const notification=d.notifications;
  const count=notification?.card_count??notification?.items?.length??0;
  if(count){
   const badge=document.createElement('span');badge.className='notification-badge';badge.textContent=String(count);
   phone.append(badge);
  }
  detail.textContent=devicePreview?'':!d.ready?'连接中':notification?.manual_control?'当前控制':notification?.protected?'草稿保护':
   notification?.state==='scanning'?'检查中':notification?.state==='paused'?'检查暂停':
   notification?.last_checked?(count?'有新通知':'暂无通知'):'待检查';
  entry.title='设备 '+number+' · '+remark.textContent+' · '+d.name+' · '+d.udid.slice(-8)+' · '+detail.textContent+' · '+count+' 张短信通知卡片'+
   (notification?.error?' · '+notification.error:notification?.last_checked?' · 最近检查：'+new Date(notification.last_checked).toLocaleString():'');
  entry.setAttribute('aria-label',entry.title);
  entry.append(phone,name,remark);if(detail.textContent)entry.append(detail);entry.onclick=()=>select(d.udid);
  const tile=document.createElement('div');tile.className='device-tile';
  tile.addEventListener('contextmenu',event=>showDeviceMenu(event,d,index));
  entry.setAttribute('aria-haspopup','menu');
  entry.addEventListener('keydown',event=>{
   if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){
    const bounds=entry.getBoundingClientRect();
    showDeviceMenu({preventDefault:()=>event.preventDefault(),clientX:bounds.left,clientY:bounds.bottom},d,index);
   }
  });
  tile.append(entry);deviceList.append(tile);
 }
 if(devicePreview){
  const device=rows.find(d=>d.udid===selected);
  const label=device?deviceLabel(device,rows.indexOf(device)):null;
  document.getElementById('screen-device').textContent=label?'· 设备 '+label.number+(label.followup?' / 待跟进':''):'';
  document.getElementById('empty').style.display='';
  for(const id of ['capture-current','refresh-messages','send-reply'])document.getElementById(id).disabled=true;
  return;
 }
 for(const d of rows){
  let card=cards.get(d.udid);
  if(!card){
   const node=document.createElement('article');node.dataset.udid=d.udid;
   const label=document.createElement('div');label.className='label';
   const name=document.createElement('span');name.textContent=d.name+' · '+d.udid.slice(-6);
   const button=document.createElement('button');button.className='pick';button.textContent='选择控制';button.onclick=()=>select(d.udid);
   label.append(name,button);node.append(label);
   const waiting=document.createElement('div');waiting.className='waiting';waiting.textContent='正在启动投屏…';node.append(waiting);
   card={node,button,waiting,frame:null,origin:'http://127.0.0.1:'+d.port};cards.set(d.udid,card);
  }
  if(!d.ready&&card.frame){
   card.frame.remove();card.frame=null;card.node.querySelector('.cover')?.remove();
   card.waiting.textContent=d.error||'投屏连接中断，正在重新连接…';card.node.append(card.waiting);
  }
  if(!d.ready)card.waiting.textContent=d.error||'正在启动投屏…';
  if(d.ready&&!card.frame){
   const frame=document.createElement('iframe');frame.title=d.name+' 实时画面';frame.src=card.origin+'/?batch=1&manager='+encodeURIComponent(location.origin);frame.allow='clipboard-read; clipboard-write';
   frame.onload=()=>sendFocus(card,active===d.udid&&!controlPaused);card.frame=frame;card.waiting.remove();card.node.append(frame);
   const cover=document.createElement('button');cover.className='cover';cover.textContent='选择 '+d.name;cover.setAttribute('aria-label','选择 '+d.name+' 进行控制');cover.onclick=()=>select(d.udid);card.node.append(cover);
  }
  const on=selected===d.udid;card.node.classList.toggle('selected',on);card.button.textContent=on?'正在控制':'选择控制';card.button.disabled=!d.ready||busy;
  const target=document.getElementById(on?'selected':'previews');if(card.node.parentElement!==target)target.append(card.node);
  const controllable=on&&!controlPaused;
  if(card.lastActive!==controllable){sendFocus(card,controllable);card.lastActive=controllable;}
 }
 const empty=document.getElementById('empty');if(empty)empty.style.display=selected?'none':'';
 const owner=rows.find(d=>d.udid===selected);
 const ownerLabel=owner?deviceLabel(owner,rows.indexOf(owner)):null;
 document.getElementById('screen-device').textContent=ownerLabel?'· 设备 '+ownerLabel.number+(ownerLabel.followup?' / 待跟进':''):'';
}
async function select(udid){
 if(devicePreview){previewSelection=udid;render(previewDevices,previewSelection);return;}
  if(busy||workspaceBusy)return;busy=true;for(const card of cards.values())sendFocus(card,false);render(latest,null);
 try{const r=await fetch('/api/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({udid})});const j=await r.json();if(!r.ok)throw Error(j.error);active=j.active;}
 catch(e){active=null;notice(e.message);}
 finally{busy=false;await refresh();}
}
async function refresh(){if(devicePreview){render(previewDevices,previewSelection);return;}try{const r=await fetch('/api/state',{cache:'no-store'});const j=await r.json();if(!busy)render(j.devices,j.active);}catch(e){notice('管理页面连接中断');}}
refresh();if(!devicePreview)setInterval(refresh,2000);
document.getElementById('screen-expand').addEventListener('click',e=>{
 const expanded=document.body.classList.toggle('screen-expanded');
 e.currentTarget.textContent=expanded?'恢复布局':'放大画面';
 e.currentTarget.setAttribute('aria-pressed',String(expanded));
});
