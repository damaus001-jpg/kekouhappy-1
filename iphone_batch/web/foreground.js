/* Foreground conversation reading. This is separate from notification scanning. */
class ForegroundSyncController {
 constructor({request,context,apply,status,clock=()=>Date.now(),client=crypto.randomUUID()}){
  Object.assign(this,{request,context,apply,status,clock,client});
  this.generation=1;this.device=null;this.number=null;this.pending=null;this.nextAt=0;
  this.seekArmed=false;
  this.sessionDevice=null;this.preparePending=null;this.prepareAt=0;this.sessionPrepared=false;
  this.prepareTask=null;this.lastProbeGeneration=-1;
  this.probeAttempts=0;this.probeRetryTimer=null;
  this.expectedSend=null;this.sendCheck=null;this.sendTimer=null;
  this.manualUntil=0;this.held=false;this.keysHeld=false;this.historyPaused=false;this.inputPaused=false;
 }
 invalidate(){
  clearTimeout(this.sendTimer);this.sendTimer=null;this.sendCheck=null;
  clearTimeout(this.probeRetryTimer);this.probeRetryTimer=null;
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
  this.expectedSend=null;
  if(device)this.request({action:'release',client:this.client,generation,device}).catch(()=>{});
 }
 prepare(context){
  if(!context.allowed){if(this.sessionDevice)this.releaseSession();return;}
  if(context.busy||this.held||this.keysHeld||this.seekArmed||this.pending||this.clock()<this.manualUntil||this.sessionPrepared||this.preparePending||this.clock()<this.prepareAt)return;
  const device=this.device,generation=this.generation,abort=new AbortController();
  this.sessionDevice=device;this.preparePending=abort;this.prepareAt=this.clock()+2000;
  this.prepareTask=this.request({action:'prepare',client:this.client,generation,device},abort.signal).then(result=>{
   if(!abort.signal.aborted&&device===this.device&&generation===this.generation){
    this.sessionPrepared=result.phase==='prepared';
    if(result.phase==='trust_required'&&!this.pending&&!this.number&&!this.seekArmed)this.showTrustRequired(result);
   }
   return result;
  }).catch(error=>({phase:'error',error})).finally(()=>{if(this.preparePending===abort){this.preparePending=null;this.prepareTask=null;}});
 }
 showTrustRequired(result){
  this.sessionPrepared=false;this.prepareAt=Infinity;this.nextAt=Infinity;
  this.status(result.message,false);
 }
 retryProbe(){
  if(this.probeAttempts>=3)return false;
  this.invalidate();this.number=null;this.seekArmed=true;
  this.nextAt=this.clock()+300;
  const generation=this.generation;
  this.probeRetryTimer=setTimeout(()=>{
   this.probeRetryTimer=null;
   if(generation===this.generation&&this.seekArmed)void this.tick();
  },300);
  this.status('会话尚未稳定，正在重试识别号码',false);
  return true;
 }
 expectSend(number,text){
  if(number)this.expectedSend={number,text};
 }
 startSendCheck(){
  const number=this.expectedSend?.number||this.number;
  if(!number||!this.context().allowed)return false;
  const expected=this.expectedSend?.text??null;
  this.invalidate();this.seekArmed=false;
  this.historyPaused=false;this.inputPaused=false;this.held=false;this.keysHeld=false;
  this.sendCheck={number,expected,attempts:0,generation:this.generation,device:this.device,
   sendExpected:!!this.expectedSend};
  void this.checkSent();
  return true;
 }
 async checkSent(){
  const task=this.sendCheck,context=this.context();
  if(!task)return;
  if(task.generation!==this.generation||task.device!==context.device||!context.allowed){
   if(this.sendCheck===task)this.sendCheck=null;
   return;
  }
  const later=()=>{
   if(this.sendCheck!==task)return;
   if(task.attempts>=3){
    this.sendCheck=null;
    if(!task.sendExpected){this.number=null;this.activity('tap-complete');return;}
    this.status('发送结果待核对，请检查手机会话',false);return;
   }
   this.sendTimer=setTimeout(()=>{this.sendTimer=null;void this.checkSent();},300);
  };
  if((context.inputBusy??context.busy)||this.pending){later();return;}
  const abort=new AbortController();this.pending=abort;task.attempts++;
  this.status('正在核对发送后的最新气泡',false);
  try{
   const result=await this.request({action:'sent_tail',client:this.client,generation:task.generation,
    device:task.device,phone_number:task.number,expected_text:task.expected},abort.signal);
   if(this.sendCheck!==task||abort.signal.aborted||this.context().device!==task.device||!this.context().allowed)return;
   if(result.phase==='send_saved'){
    this.sendCheck=null;this.expectedSend=null;this.number=result.phone_number;this.nextAt=this.clock()+2000;
    this.apply(result);this.status('已确认发送并更新最新气泡',false);return;
   }
   if(result.phase==='trust_required'){this.sendCheck=null;this.showTrustRequired(result);return;}
   if(result.phase==='send_changed'){
    this.sendCheck=null;this.expectedSend=null;this.number=null;
    this.activity('tap-complete');return;
   }
   if(result.phase==='cancelled'){
    this.sendCheck=null;this.expectedSend=null;this.status('会话已变化，本次发送结果待核对',false);return;
   }
   later();
  }catch(error){if(!abort.signal.aborted)later();}
  finally{if(this.pending===abort)this.pending=null;}
 }
 activity(kind,details={}){
  this.retarget(this.context().device);
  clearTimeout(this.probeRetryTimer);this.probeRetryTimer=null;
  const now=this.clock();
  if(kind==='send-complete'){
   this.startSendCheck();return;
  }
  if(kind==='tap-complete'){
   const context=this.context();
   if(!context.allowed)return;
   if(!this.historyPaused&&(this.expectedSend||this.number)&&this.startSendCheck())return;
   if(this.lastProbeGeneration===this.generation)this.invalidate();
   this.nextAt=0;
   this.probeAttempts=0;
   this.number=null;this.seekArmed=true;this.historyPaused=false;this.inputPaused=false;
   this.manualUntil=now;this.held=false;this.keysHeld=false;
   this.apply({phase:'identified',conversations:[]});
   this.status('点击已确认，正在识别会话号码',false);
   setTimeout(()=>void this.tick(),0);
   return;
  }
  if(this.sendCheck)this.invalidate();
  this.seekArmed=false;
  if(kind==='select'){this.releaseSession();this.number=null;}
  if(this.pending)this.invalidate();
  this.manualUntil=now+(kind==='pointer-start'||kind==='pointer-end'?400:1800);
  if(kind==='pointer-start'){this.held=true;this.inputPaused=false;}
  if(kind==='pointer-end')this.held=false;
  if(kind==='key-state')this.keysHeld=details.keysHeld===true;
  if(kind==='scroll')this.historyPaused=true;
  if(kind==='select'){this.historyPaused=false;this.inputPaused=false;this.held=false;this.keysHeld=false;}
  if(kind==='key'||kind==='paste')this.inputPaused=false;
  if(kind==='key'&&this.number&&!this.expectedSend)this.expectedSend={number:this.number,text:null};
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
  if(this.sendCheck)return;
  this.prepare(context);
  if(!this.number&&!this.seekArmed){
   if(this.nextAt!==Infinity)this.status(context.allowed?'点击短信会话以识别号码':!context.allowed?'等待当前手机操作区可见':'等待手机画面点击',false);
   return;
  }
  const paused=!context.allowed||context.busy||this.held||this.keysHeld||this.historyPaused||this.inputPaused||this.clock()<this.manualUntil;
  if(paused){
   if(this.pending)this.invalidate();
   if(!this.number&&!(context.allowed&&context.busy&&this.seekArmed))this.seekArmed=false;
   this.status(this.historyPaused?'手机滚动后已暂停':this.inputPaused?'手机输入框已有草稿，已暂停':context.busy?'正在人工操作，自动读取让路':!context.allowed?'等待当前手机操作区可见':'等待人工操作结束',this.historyPaused||this.inputPaused);
   return;
  }
  if(this.pending||this.clock()<this.nextAt)return;
  const device=this.device,generation=this.generation,abort=new AbortController();
  const action=this.number?'tick':'probe';
  this.sessionDevice=device;
  if(action==='probe'){this.seekArmed=false;this.lastProbeGeneration=generation;this.probeAttempts++;}
  this.pending=abort;
  this.status(action==='probe'?'正在识别刚点击的会话号码':'正在检查当前会话更新',false);
  try{
   if(action==='probe'&&this.prepareTask)await this.prepareTask;
   if(generation!==this.generation||abort.signal.aborted)return;
   const result=await this.request({action,client:this.client,generation,device,
    ...(action==='probe'?{probe_attempt:this.probeAttempts}:{})},abort.signal);
   const current=this.context();
   if(generation!==this.generation||device!==current.device||!current.allowed||abort.signal.aborted)return;
   if(current.busy){if(action==='probe')this.retryProbe();return;}
   if(result.phase==='trust_required'){this.showTrustRequired(result);return;}
   if(action==='probe'&&['not_found','busy','awaiting_tap','error'].includes(result.phase)&&this.retryProbe())return;
   this.nextAt=result.phase==='not_found'?Infinity:this.clock()+Math.max(300,Number(result.next_seconds||2)*1000);
   if(result.phase==='error'){
    this.sessionPrepared=false;
    if(action==='probe')this.nextAt=Infinity;
   }
   if(result.clear_conversation){this.number=null;this.seekArmed=false;}
   if(result.phone_number)this.number=result.phone_number;
   if(result.conversations)this.apply(result);
   if(result.phase==='input_paused')this.inputPaused=true;
   const labels={identified:'已识别号码，准备自动读取',not_found:'本次未识别，等待下一次手机画面点击',awaiting_tap:'点击手机会话以识别号码',saved:'已保存本轮消息，等待更新',waiting:result.message||'等待当前会话更新',
    changed:'发现变化，准备补读',unconfirmed:'气泡衔接未确认，历史已保留',seeking:'等待打开短信会话',
    busy:action==='probe'?'本次未识别：人工任务繁忙，等待下一次手机画面点击':'人工任务优先，稍后继续',input_paused:'手机输入框已有草稿，已暂停',error:result.message||'读取未完成'};
   this.status(labels[result.phase]||'等待当前会话更新',this.inputPaused);
  }catch(error){
   if(!abort.signal.aborted&&generation===this.generation&&action==='probe'&&this.retryProbe())return;
   if(!abort.signal.aborted&&generation===this.generation){this.nextAt=Infinity;this.seekArmed=false;this.status('本次识别未完成，请再次点击手机会话重试',false);}
  }finally{if(this.pending===abort)this.pending=null;}
 }
}

if(typeof module!=='undefined'&&module.exports)module.exports={ForegroundSyncController};
else {
 const status=document.getElementById('foreground-status'),resume=document.getElementById('foreground-resume');
 function applyForeground(result){
  if(workspaceBusy||phonePastePending||(draftEl.value.trim()&&!result.after_send)||workspaceDevice!==active)return;
  const records=result.conversations||[];
  const keptDraft=draftEl.value,keptBlocked=sendBlocked;
  if(currentConversationId===(records[0]?.id||null)&&currentConversation?.phone_number===window.ForegroundSync.number)return;
  const containers=[messagesEl,document.querySelector('.work-panel')].filter(Boolean);
  const sameNumber=currentConversation?.phone_number===window.ForegroundSync.number;
  const positions=containers.map(node=>({node,top:node.scrollTop||0,
   bottom:node.scrollHeight-node.clientHeight-(node.scrollTop||0)<32}));
  ++workspaceRevision;savedConversations=records;currentConversationId=records[0]?.id||null;
  renderConversation();
  if(result.after_send){draftEl.value=keptDraft;sendBlocked=keptBlocked;resizeDraft();syncWorkspaceControls();}
  if(!currentConversation)document.getElementById('peer-phone').textContent=window.ForegroundSync.number||'—';
  for(const {node,top,bottom} of positions)node.scrollTop=!sameNumber||bottom?node.scrollHeight:top;
 }
 window.ForegroundSync=new ForegroundSyncController({
  request:async(body,signal)=>{
   const response=await fetch('/api/foreground',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(80000)]):AbortSignal.timeout(10000),keepalive:['cancel','release'].includes(body.action)});
   const result=await response.json();if(!response.ok||result.error)throw Error(result.error||'自动读取请求失败');return result;
  },
  context:()=>{
   const device=latest.find(row=>row.udid===active),rect=phoneViewport.getBoundingClientRect();
   return {device:active,allowed:!!(active&&workspaceDevice===active&&!devicePreview&&!document.hidden&&
    controlOwner===active&&device?.ready&&device.enabled!==false&&!device.readonly&&rect.bottom>0&&rect.top<window.innerHeight),
    busy:busy||workspaceBusy||!!phonePastePending||!!draftEl.value.trim()||!!generatedDraft||refreshingDevices,
    inputBusy:busy||workspaceBusy||!!phonePastePending||refreshingDevices};
  },apply:applyForeground,
  status:(text,paused)=>{status.textContent='自动读取：'+text;resume.hidden=!paused;}
 });
 resume.addEventListener('click',()=>window.ForegroundSync.resume());
 window.addEventListener('message',event=>{
  if(event.data?.type!=='phone-activity')return;
  const card=cards.get(active);
  if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
  if(['pointer-start','pointer-end','tap-complete','send-complete','scroll','key','key-state','paste'].includes(event.data.kind))window.ForegroundSync.activity(event.data.kind,{keysHeld:event.data.keysHeld===true});
 });
 document.addEventListener('visibilitychange',()=>{if(document.hidden)window.ForegroundSync.stop();});
 const timer=setInterval(()=>void window.ForegroundSync.tick(),500);
 window.addEventListener('pagehide',()=>{clearInterval(timer);window.ForegroundSync.stop();});
}
