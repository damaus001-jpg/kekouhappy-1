
const cards=new Map();let active=null;let busy=false;let latest=[];let controlPaused=false;
const status=document.getElementById('status');
function sendFocus(card,on){if(card.frame) card.frame.contentWindow.postMessage({type:'device-focus',active:on},card.origin);}
function render(rows,selected){
 latest=rows;active=selected;
 controlPaused=rows.some(row=>row.udid===selected&&row.notifications?.state==='scanning');
 loadWorkspace(selected);
 document.getElementById('device-count').textContent=rows.length+' 台';
 const deviceList=document.getElementById('device-list');deviceList.replaceChildren();
 for(const d of rows){
  const entry=document.createElement('button');entry.type='button';entry.className='device-entry'+(selected===d.udid?' current':'');entry.disabled=!d.ready||busy;entry.setAttribute('aria-pressed',String(selected===d.udid));
  const name=document.createElement('strong');name.textContent=d.name;
  const detail=document.createElement('span');detail.textContent=d.udid.slice(-8)+' · '+(d.ready?(selected===d.udid?'当前控制':'可选择'):'投屏启动中');
  const alerts=document.createElement('span');const notification=d.notifications;
  alerts.textContent=notification?.pending_contacts?'● '+notification.pending_contacts+' 个待处理短信联系人':notification?.last_checked?'暂无待处理通知':'通知待检查';
  if(notification?.protected)alerts.textContent+=' · 草稿保护中';
  else if(notification?.state==='scanning')alerts.textContent+=' · 检查中';
  else if(notification?.state==='paused')alerts.textContent+=' · 检查暂停';
  alerts.title=notification?.error||(notification?.last_checked?'最近检查：'+new Date(notification.last_checked).toLocaleString():'最多4台并行检查，每台检查后间隔30秒');
  entry.append(name,detail,alerts);entry.onclick=()=>select(d.udid);deviceList.append(entry);
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
 document.getElementById('screen-device').textContent=owner?'· '+owner.name:'';
 if(owner?.notifications)applyNotificationSnapshot(owner.notifications);
 status.textContent=busy?'正在切换控制…':controlPaused?'正在后台检查短信通知，手机控制稍后恢复':`${rows.filter(d=>d.ready).length}/${rows.length} 台页面就绪 · ${owner?'当前控制：'+owner.name:'请选择一台手机'}`;
}
async function select(udid){
  if(busy||workspaceBusy)return;busy=true;for(const card of cards.values())sendFocus(card,false);render(latest,null);
 try{const r=await fetch('/api/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({udid})});const j=await r.json();if(!r.ok)throw Error(j.error);active=j.active;}
 catch(e){active=null;status.textContent=e.message;}
 finally{busy=false;await refresh();}
}
async function refresh(){try{const r=await fetch('/api/state',{cache:'no-store'});const j=await r.json();if(!busy)render(j.devices,j.active);}catch(e){status.textContent='管理页面连接中断';}}
refresh();setInterval(refresh,2000);
document.getElementById('screen-expand').addEventListener('click',e=>{
 const expanded=document.body.classList.toggle('screen-expanded');
 e.currentTarget.textContent=expanded?'恢复布局':'放大画面';
 e.currentTarget.setAttribute('aria-pressed',String(expanded));
});
