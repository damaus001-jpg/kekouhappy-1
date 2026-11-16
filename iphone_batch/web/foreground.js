/* Foreground conversation reading. This is separate from notification scanning. */
class ForegroundSyncController {
 constructor({request,context,apply,status,clock=()=>Date.now(),client=crypto.randomUUID()}){
  Object.assign(this,{request,context,apply,status,clock,client});
  this.generation=1;this.device=null;this.number=null;this.pending=null;this.nextAt=0;
  this.seekArmed=false;
  this.sessionDevice=null;this.preparePending=null;this.prepareAt=0;this.sessionPrepared=false;
  this.manualUntil=0;this.held=false;this.keysHeld=false;this.historyPaused=false;this.inputPaused=false;
 }
 invalidate(){
  const generation=this.generation++;
  this.pending?.abort();
  this.request({action:'cancel',client:this.client,generation}).catch(()=>{});
  this.nextAt=0;
 }
 retarget(device){
  if(device===this.device)return;
  this.releaseSession();this.device=device;this.number=null;this.seekArmed=false;this.historyPaused=false;this.inputPaused=false;this.held=false;this.keysHeld=false;
 }
 releaseSession(){
  const device=this.sessionDevice,generation=this.generation;
  this.preparePending?.abort();this.preparePending=null;
  this.sessionDevice=null;this.sessionPrepared=false;this.prepareAt=0;
  this.invalidate();this.seekArmed=false;
  if(device)this.request({action:'release',client:this.client,generation,device}).catch(()=>{});
 }
 prepare(context){
  if(!context.allowed){if(this.sessionDevice)this.releaseSession();return;}
  if(context.busy||this.held||this.keysHeld||this.seekArmed||this.pending||this.clock()<this.manualUntil||this.sessionPrepared||this.preparePending||this.clock()<this.prepareAt)return;
  const device=this.device,generation=this.generation,abort=new AbortController();
  this.sessionDevice=device;this.preparePending=abort;this.prepareAt=this.clock()+2000;
  this.request({action:'prepare',client:this.client,generation,device},abort.signal).then(result=>{
   if(!abort.signal.aborted&&device===this.device&&generation===this.generation)this.sessionPrepared=result.phase==='prepared';
  }).catch(()=>{}).finally(()=>{if(this.preparePending===abort)this.preparePending=null;});
 }
 activity(kind,details={}){
  this.retarget(this.context().device);
  const now=this.clock();
  if(kind==='tap-complete'){
   const context=this.context();
   if(!context.allowed||context.busy){this.status('手机画面已点击，但当前任务繁忙；再点一次会话以寻号',false);return;}
   this.invalidate();this.number=null;this.seekArmed=true;this.historyPaused=false;this.inputPaused=false;
   this.manualUntil=now;this.held=false;this.keysHeld=false;
   this.apply({phase:'identified',conversations:[]});
   this.status('点击已确认，正在识别会话号码',false);
   setTimeout(()=>void this.tick(),0);
   return;
  }
  this.seekArmed=false;
  if(kind==='select'){this.releaseSession();this.number=null;}
  if(this.pending||now>=this.manualUntil)this.invalidate();
  this.manualUntil=now+(kind==='pointer-start'||kind==='pointer-end'?400:1800);
  if(kind==='pointer-start'){this.held=true;this.inputPaused=false;}
  if(kind==='pointer-end')this.held=false;
  if(kind==='key-state')this.keysHeld=details.keysHeld===true;
  if(kind==='scroll')this.historyPaused=true;
  if(kind==='select'){this.historyPaused=false;this.inputPaused=false;this.held=false;this.keysHeld=false;}
  if(kind==='key'||kind==='paste')this.inputPaused=false;
 }
 resume(){
  this.historyPaused=false;this.inputPaused=false;this.held=false;this.manualUntil=this.clock()+300;
  this.invalidate();
  if(!this.number){this.seekArmed=false;this.status('点击手机会话以识别号码',false);}
 }
 stop(){this.releaseSession();this.held=false;this.keysHeld=false;}
 async tick(){
  const context=this.context();
  this.retarget(context.device);
  this.prepare(context);
  if(!this.number&&!this.seekArmed){
   this.status(context.allowed?'点击短信会话以识别号码':!context.allowed?'等待当前手机操作区可见':'等待手机画面点击',false);
   return;
  }
  const paused=!context.allowed||context.busy||this.held||this.keysHeld||this.historyPaused||this.inputPaused||this.clock()<this.manualUntil;
  if(paused){
   if(this.pending)this.invalidate();
   if(!this.number)this.seekArmed=false;
   this.status(this.historyPaused?'手机滚动后已暂停':this.inputPaused?'手机输入框已有草稿，已暂停':context.busy?'正在人工操作，自动读取让路':!context.allowed?'等待当前手机操作区可见':'等待人工操作结束',this.historyPaused||this.inputPaused);
   return;
  }
  if(this.pending||this.clock()<this.nextAt)return;
  const device=this.device,generation=this.generation,abort=new AbortController();
  const action=this.number?'tick':'probe';
  this.sessionDevice=device;
  if(action==='probe')this.seekArmed=false;
  this.pending=abort;
  this.status(action==='probe'?'正在识别刚点击的会话号码':'正在检查当前会话更新',false);
  try{
   const result=await this.request({action,client:this.client,generation,device},abort.signal);
   const current=this.context();
   if(generation!==this.generation||device!==current.device||!current.allowed||current.busy||abort.signal.aborted)return;
   this.nextAt=result.phase==='not_found'?Infinity:this.clock()+Math.max(300,Number(result.next_seconds||2)*1000);
   if(result.phase==='error')this.sessionPrepared=false;
   if(result.clear_conversation){this.number=null;this.seekArmed=false;}
   if(result.phone_number)this.number=result.phone_number;
   if(result.conversations)this.apply(result);
   if(result.phase==='input_paused')this.inputPaused=true;
   const labels={identified:'已识别号码，准备自动读取',not_found:'本次未识别，等待下一次手机画面点击',awaiting_tap:'点击手机会话以识别号码',saved:'已保存本轮消息，等待更新',waiting:result.message||'等待当前会话更新',
    changed:'发现变化，准备补读',unconfirmed:'气泡衔接未确认，历史已保留',seeking:'等待打开短信会话',
    busy:action==='probe'?'本次未识别：人工任务繁忙，等待下一次手机画面点击':'人工任务优先，稍后继续',input_paused:'手机输入框已有草稿，已暂停',error:result.message||'读取未完成'};
   this.status(labels[result.phase]||'等待当前会话更新',this.inputPaused);
  }catch(error){
   if(!abort.signal.aborted&&generation===this.generation){this.nextAt=Infinity;this.seekArmed=false;this.status('本次识别未完成，请再次点击手机会话重试',false);}
  }finally{if(this.pending===abort)this.pending=null;}
 }
}

if(typeof module!=='undefined'&&module.exports)module.exports={ForegroundSyncController};
else {
 const status=document.getElementById('foreground-status'),resume=document.getElementById('foreground-resume');
 function applyForeground(result){
  if(workspaceBusy||phonePastePending||draftEl.value.trim()||workspaceDevice!==active)return;
  const records=result.conversations||[];
  if(currentConversationId===(records[0]?.id||null)&&currentConversation?.phone_number===window.ForegroundSync.number)return;
  const containers=[messagesEl,document.querySelector('.work-panel')].filter(Boolean);
  const sameNumber=currentConversation?.phone_number===window.ForegroundSync.number;
  const positions=containers.map(node=>({node,top:node.scrollTop||0,
   bottom:node.scrollHeight-node.clientHeight-(node.scrollTop||0)<32}));
  ++workspaceRevision;savedConversations=records;currentConversationId=records[0]?.id||null;
  renderConversation();
  if(!currentConversation)document.getElementById('peer-phone').textContent=window.ForegroundSync.number||'—';
  for(const {node,top,bottom} of positions)node.scrollTop=!sameNumber||bottom?node.scrollHeight:top;
 }
 window.ForegroundSync=new ForegroundSyncController({
  request:async(body,signal)=>{
   const response=await fetch('/api/foreground',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(38000)]):AbortSignal.timeout(10000),keepalive:['cancel','release'].includes(body.action)});
   const result=await response.json();if(!response.ok||result.error)throw Error(result.error||'自动读取请求失败');return result;
  },
  context:()=>{
   const device=latest.find(row=>row.udid===active),rect=phoneViewport.getBoundingClientRect();
   return {device:active,allowed:!!(active&&workspaceDevice===active&&!devicePreview&&!document.hidden&&
    controlOwner===active&&device?.ready&&device.enabled!==false&&!device.readonly&&rect.bottom>0&&rect.top<window.innerHeight),
    busy:busy||workspaceBusy||!!phonePastePending||!!draftEl.value.trim()||!!generatedDraft||refreshingDevices};
  },apply:applyForeground,
  status:(text,paused)=>{status.textContent='自动读取：'+text;resume.hidden=!paused;}
 });
 resume.addEventListener('click',()=>window.ForegroundSync.resume());
 window.addEventListener('message',event=>{
  if(event.data?.type!=='phone-activity')return;
  const card=cards.get(active);
  if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
  if(['pointer-start','pointer-end','tap-complete','scroll','key','key-state','paste'].includes(event.data.kind))window.ForegroundSync.activity(event.data.kind,{keysHeld:event.data.keysHeld===true});
 });
 document.addEventListener('visibilitychange',()=>{if(document.hidden)window.ForegroundSync.stop();});
 const timer=setInterval(()=>void window.ForegroundSync.tick(),500);
 window.addEventListener('pagehide',()=>{clearInterval(timer);window.ForegroundSync.stop();});
}
