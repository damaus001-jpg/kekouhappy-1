
const cards=new Map();let active=null;let busy=false;let latest=[];let controlPaused=false;
let selectionRevision=0;
let controlOwner=null;
const devicePreview=location.hash==='#preview-devices';
const autoScanSwitch=document.getElementById('auto-scan');
const autoScanStatus=document.getElementById('auto-scan-status');
let autoScanEnabled=true,autoScanUpdating=false,scanRevision=0;
function syncAutoScan(enabled){
 if(typeof enabled!=='boolean'||autoScanUpdating)return;
 autoScanEnabled=enabled;
 if(autoScanSwitch){autoScanSwitch.checked=enabled;autoScanSwitch.disabled=devicePreview;}
 if(autoScanStatus)autoScanStatus.textContent=enabled?'已开启':'已关闭';
}
autoScanSwitch?.addEventListener('change',async()=>{
 if(autoScanUpdating||devicePreview)return;
 const enabled=autoScanSwitch.checked;
 autoScanUpdating=true;scanRevision++;autoScanSwitch.disabled=true;
 autoScanStatus.textContent=enabled?'正在开启…':'正在停止…';
 try{
  const response=await fetch('/api/notification-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});
  const result=await response.json();
  if(!response.ok||typeof result.enabled!=='boolean')throw Error(result.error||'遍历开关未完成，请重试');
  autoScanEnabled=result.enabled;render(latest,active);
  notice(result.enabled?'自动遍历已开启':'自动遍历已关闭，可以测试投屏操作速度。');
 }catch(error){notice(error.message);}
 finally{autoScanUpdating=false;scanRevision++;syncAutoScan(autoScanEnabled);refresh();}
});
let refreshingDevices=false,deviceRefreshQueued=false;
const refreshDevicesButton=document.getElementById('refresh-devices');
function syncDeviceRefreshControls(){
 if(!refreshDevicesButton)return;
 refreshDevicesButton.disabled=refreshingDevices;
 refreshDevicesButton.textContent=refreshingDevices?'…':deviceRefreshQueued?'↻…':'↻';
 refreshDevicesButton.title=deviceRefreshQueued?'已安排刷新，等待当前操作结束':refreshingDevices?'正在重新检测 USB 手机':'重新检测 USB 手机';
 refreshDevicesButton.setAttribute('aria-busy',String(refreshingDevices||deviceRefreshQueued));
 if(deviceRefreshQueued&&!busy&&!workspaceBusy&&!refreshingDevices)void refreshDevices();
}
async function deviceRequest(url,options,timeout=15000){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
 try{
  const response=await fetch(url,{...options,signal:controller.signal});
  const result=await response.json();if(!response.ok)throw Error(result.error||'设备操作失败');
  return result;
 }catch(error){if(error.name==='AbortError')throw Error('设备操作超时，请检查连接后刷新重试。');throw error;}
 finally{clearTimeout(timer);}
}
async function refreshDevices(){
 if(refreshingDevices)return;
 if(devicePreview){render(previewDevices,previewSelection);notice('预览模式：已刷新模拟设备');return;}
 if(busy||workspaceBusy){
  deviceRefreshQueued=true;syncDeviceRefreshControls();
  notice('当前操作尚未结束，已安排设备刷新；结束后自动检查连接。');return;
 }
 deviceRefreshQueued=false;refreshingDevices=true;syncDeviceRefreshControls();
 notice('正在重新检测 USB 并检查当前手机连接…');
 try{
  const result=await deviceRequest('/api/devices/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  await refresh();
  if(active&&controlOwner!==active&&latest.some(d=>d.udid===active&&d.ready)){
   const selectedState=await deviceRequest('/api/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({udid:active})});
   controlOwner=selectedState.active;render(latest,selectedState.selected??selectedState.active,controlOwner);
  }
  notice('已重新检测 USB：当前识别到 '+result.count+' 台手机。');
  const card=cards.get(active);
  if(card?.frame&&controlOwner===active)card.frame.contentWindow.postMessage({type:'input-recover'},card.origin);
 }catch(error){notice(error.message);}
 finally{refreshingDevices=false;syncDeviceRefreshControls();}
}
refreshDevicesButton?.addEventListener('click',refreshDevices);
const phoneHomeButton=document.getElementById('phone-home');
phoneHomeButton?.addEventListener('click',()=>{
 if(!active||controlOwner!==active||busy||workspaceBusy||controlPaused||devicePreview)return;
 const card=cards.get(active);
 if(!card?.frame){notice('手机画面尚未连接，请稍后重试');return;}
 card.frame.contentWindow.postMessage({type:'device-home'},card.origin);
});
window.addEventListener('message',event=>{
 if(event.data?.type==='input-health-result'){
  const card=cards.get(active);
  if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
  const state=event.data;
  card.inputReady=state.ready===true;
  syncWorkspaceControls();
  if(card.connectionNotice){
   card.connectionNotice.hidden=state.ready===true||state.state==='inactive';
   card.connectionNotice.textContent=state.state==='unavailable'?'控制连接不可用，点击设备列表刷新重试':'控制连接检查与恢复中…';
  }
  if(state.manual&&state.ready)notice('当前设备控制连接已检查'+(state.recovered?'并恢复':'，可正常操作')+'。');
  return;
 }
 if(event.data?.type!=='device-home-result')return;
 const card=cards.get(active);
 if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
 notice(event.data.ok?'已请求返回手机主页':event.data.error||'返回手机主页失败，请检查手机连接');
});
let revealingDeveloperMode=false;
let developerModeFeedbackDevice=null;
const revealDeveloperModeButton=document.getElementById('reveal-developer-mode');
const developerModeStatus=document.getElementById('developer-mode-status');
function syncDeveloperModeButton(){
 if(!revealDeveloperModeButton)return;
 revealDeveloperModeButton.disabled=!active||busy||workspaceBusy||revealingDeveloperMode||devicePreview;
 revealDeveloperModeButton.textContent=revealingDeveloperMode?'正在显示入口…':'显示开发者模式入口';
 if(developerModeFeedbackDevice!==active){
  developerModeFeedbackDevice=active;
  developerModeStatus.textContent=active?'仅显示当前手机的设置入口；请在手机上手动开启。':'选中手机后点击，再到手机设置中开启开发者模式。';
 }
}
revealDeveloperModeButton?.addEventListener('click',async()=>{
 if(!active||busy||workspaceBusy||revealingDeveloperMode||devicePreview)return;
 const device=active;
 const row=latest.find(d=>d.udid===device);
 const label=row?deviceLabel(row,latest.indexOf(row)).number:device.slice(-8);
 revealingDeveloperMode=true;syncDeveloperModeButton();
 developerModeStatus.textContent='正在为设备 '+label+' 显示入口…';
 try{
  const response=await fetch('/api/developer-mode/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device})});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'显示入口失败，请检查手机连接后重试');
  if(active===device)developerModeStatus.textContent='设备 '+label+'：'+result.message;
 }catch(error){if(active===device)developerModeStatus.textContent='设备 '+label+'：'+error.message;}
 finally{revealingDeveloperMode=false;syncDeveloperModeButton();}
});
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
  notice('手机已打开 '+number+'；'+(result.scope||'已读取会话原文'));
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
function sendFocus(card,on){if(card.frame) card.frame.contentWindow.postMessage({type:'device-focus',active:on,visible:card.node.parentElement?.id==='selected'&&!card.node.hidden,working:workspaceBusy},card.origin);}
function releasePreview(card){
 if(!card.frame)return;
 sendFocus(card,false);
 card.frame.onload=null;card.frame.remove();card.frame=null;
 card.cover?.remove();card.cover=null;
 card.connectionNotice?.remove();card.connectionNotice=null;
 card.inputReady=false;
 card.lastActive=undefined;card.lastVisible=undefined;card.lastWorking=undefined;
}
function render(rows,selected,controller=controlOwner){
 latest=rows;active=selected;controlOwner=controller;
 syncDeviceRefreshControls();
 const connected=new Set(rows.map(device=>device.udid));
 // Release the old page before opening the next one, including its decoder,
 // video subscriptions, audio and recovery timers. Hiding an iframe is insufficient.
 for(const [udid,card] of cards){
  if(udid!==selected||!rows.some(d=>d.udid===udid&&d.ready))releasePreview(card);
  if(!connected.has(udid)){card.node.remove();cards.delete(udid);}
 }
 syncDeveloperModeButton();
 controlPaused=autoScanEnabled&&rows.some(row=>row.udid===selected&&row.notifications?.state==='scanning');
 if(phoneHomeButton)phoneHomeButton.disabled=!(controlOwner===selected&&rows.some(row=>row.udid===selected&&row.ready))||busy||workspaceBusy||controlPaused||devicePreview;
 const selectedDevice=rows.find(device=>device.udid===selected);
 const readingDeviceLabel=selectedDevice?deviceLabel(selectedDevice,rows.indexOf(selectedDevice)):null;
 document.getElementById('reading-device-number').textContent='设备：'+(readingDeviceLabel?.number||'—');
 if(devicePreview)loadPreviewContacts(selectedDevice);else{loadWorkspace(selected);syncWorkspaceControls();}
 syncContactFollowup();
 document.getElementById('device-count').textContent=rows.length+' 台';
 const deviceList=document.getElementById('device-list');deviceList.replaceChildren();
 const ordered=rows.map((device,index)=>({device,index,label:deviceLabel(device,index),followupCount:contactFollowupCount(device)}));
 ordered.sort((a,b)=>{
  const available=Number(b.device.ready===true)-Number(a.device.ready===true);
  if(available)return available;
  return sortControl.value==='unread'?
   ((b.device.notifications?.card_count??b.device.notifications?.items?.length??0)-(a.device.notifications?.card_count??a.device.notifications?.items?.length??0)||a.index-b.index):
   (b.followupCount-a.followupCount||a.index-b.index);
 });
 for(const {device:d,index,label,followupCount} of ordered){
  const entry=document.createElement('button');entry.type='button';entry.className='device-entry'+(selected===d.udid?' current':'');entry.disabled=busy||workspaceBusy||refreshingDevices;entry.setAttribute('aria-pressed',String(selected===d.udid));
  entry.dataset.udid=d.udid;
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
  const setupError=String(d.error||'');
  const setupState=setupError.includes('开发者模式未开启')?'开发者模式关闭':setupError.includes('信任')?'需解锁并信任':setupError.includes('镜像准备失败')?'投屏准备失败':'正在准备投屏';
  detail.textContent=devicePreview?'':!d.ready?setupState:notification?.manual_control?'当前控制':!autoScanEnabled?'遍历已关闭':notification?.protected?'草稿保护':
   notification?.state==='scanning'?'检查中':notification?.state==='paused'?'检查暂停':
   notification?.last_checked?(count?'有新通知':'暂无通知'):'待检查';
  entry.title='设备 '+number+' · '+remark.textContent+' · '+d.name+' · '+d.udid.slice(-8)+' · '+detail.textContent+' · '+count+' 张短信通知卡片'+
   (d.error?' · '+d.error:notification?.error?' · '+notification.error:notification?.last_checked?' · 最近检查：'+new Date(notification.last_checked).toLocaleString():'');
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
  if(!d.ready)card.waiting.textContent=d.error||'正在启动投屏…';
  if(d.ready&&selected===d.udid&&!card.frame){
   card.inputReady=false;
   const frame=document.createElement('iframe');frame.title=d.name+' 实时画面';frame.src=card.origin+'/?batch=1&manager='+encodeURIComponent(location.origin);frame.allow='clipboard-read; clipboard-write';
   frame.onload=()=>sendFocus(card,controlOwner===d.udid&&active===d.udid&&!controlPaused&&!busy);card.frame=frame;card.waiting.remove();card.node.append(frame);
   const cover=document.createElement('button');cover.className='cover';cover.textContent='选择 '+d.name;cover.setAttribute('aria-label','选择 '+d.name+' 进行控制');cover.onclick=()=>select(d.udid);card.cover=cover;card.node.append(cover);
   const connectionNotice=document.createElement('div');connectionNotice.className='input-connection-status';connectionNotice.setAttribute('role','status');connectionNotice.textContent='控制连接检查中…';card.connectionNotice=connectionNotice;card.node.append(connectionNotice);
  }
  if(!card.frame&&card.waiting.parentElement!==card.node)card.node.append(card.waiting);
  const on=selected===d.udid;card.node.classList.toggle('selected',on);card.button.textContent=on&&controlOwner===d.udid?'正在控制':'选择控制';card.button.disabled=!d.ready||busy;
  const target=document.getElementById('selected');if(card.node.parentElement!==target)target.append(card.node);
  card.node.hidden=!on;
  const controllable=on&&controlOwner===d.udid&&!controlPaused&&!busy;
  if(card.lastActive!==controllable||card.lastVisible!==on||card.lastWorking!==workspaceBusy){sendFocus(card,controllable);card.lastActive=controllable;card.lastVisible=on;card.lastWorking=workspaceBusy;}
 }
 const empty=document.getElementById('empty');if(empty)empty.style.display=selected?'none':'';
 const owner=rows.find(d=>d.udid===selected);
 const ownerLabel=owner?deviceLabel(owner,rows.indexOf(owner)):null;
 document.getElementById('screen-device').textContent=ownerLabel?'· 设备 '+ownerLabel.number+(ownerLabel.followup?' / 待跟进':''):'';
}
async function select(udid){
 if(devicePreview){previewSelection=udid;render(previewDevices,previewSelection);return;}
  if(busy||workspaceBusy||refreshingDevices)return;selectionRevision++;busy=true;for(const card of cards.values()){sendFocus(card,false);card.lastActive=false;}render(latest,active);
 try{const j=await deviceRequest('/api/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({udid})});active=j.selected??j.active;controlOwner=j.active;}
 catch(e){active=null;controlOwner=null;notice(e.message);}
 finally{busy=false;render(latest,active);refresh();}
}
async function refresh(){if(devicePreview){syncAutoScan(false);render(previewDevices,previewSelection);return;}const revision=selectionRevision,scanVersion=scanRevision;try{const j=await deviceRequest('/api/state',{cache:'no-store'},8000);if(scanVersion===scanRevision)syncAutoScan(j.scan_enabled);if(!busy&&revision===selectionRevision)render(j.devices,j.selected??j.active,j.active);}catch(e){notice('管理页面连接中断');}}
refresh();if(!devicePreview)setInterval(refresh,2000);
document.getElementById('screen-expand').addEventListener('click',e=>{
 const expanded=document.body.classList.toggle('screen-expanded');
 e.currentTarget.textContent=expanded?'恢复布局':'放大画面';
 e.currentTarget.setAttribute('aria-pressed',String(expanded));
});
