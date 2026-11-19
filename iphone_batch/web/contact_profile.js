const CONTACT_PROFILE_FIELDS=['日期','姓名','年龄','工作','地区','婚否','爱好'];
if(typeof module!=='undefined'&&module.exports)module.exports={CONTACT_PROFILE_FIELDS};

if(typeof document!=='undefined'){
 const inputs=CONTACT_PROFILE_FIELDS.map((name,index)=>document.getElementById('contact-profile-field-'+index));
 let currentKey=null,currentTarget=null,revision=0,loaded=false,pending=null,timer=null;
 let saveQueue=Promise.resolve();
 function context(){
  if(typeof currentConversation==='undefined'||!currentConversation)return null;
  const preview=typeof devicePreview!=='undefined'&&devicePreview;
  const device=preview?previewLoadedDevice:workspaceDevice;if(!device)return null;
  const raw=String(currentConversation.phone_number||currentConversation.contact||''),digits=raw.replace(/\D/g,'');
  const phone=/^\+?[\d ()-]+$/.test(raw)?(raw.startsWith('+')&&digits.length>=7&&digits.length<=15?'+'+digits:digits.length===10?'+1'+digits:digits.length===11&&digits.startsWith('1')?'+'+digits:null):null;
  return {device,preview,conversation:currentConversation.id,key:(preview?'preview:':'device:')+device+':'+(phone||currentConversation.id)};
 }
 function readForm(){return Object.fromEntries(CONTACT_PROFILE_FIELDS.map((name,index)=>[name,inputs[index].value]));}
 function writeForm(fields={}){for(const [index,name] of CONTACT_PROFILE_FIELDS.entries())inputs[index].value=fields[name]??(name==='爱好'?fields['兴趣爱好']:'')??'';}
 function draftKey(target){return 'iphone-contact-profile-draft:'+target.key;}
 function reportSaveError(error){if(typeof window.notice==='function')window.notice('联系人资料保存失败：'+error.message);}
 function persist(job){
  saveQueue=saveQueue.catch(()=>{}).then(async()=>{
   let result;
   if(job.target.preview){result={fields:job.fields,updated:new Date().toISOString()};localStorage.setItem('iphone-contact-profile:'+job.target.key,JSON.stringify(result));}
   else{
    const response=await fetch('/api/contact-profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:job.target.device,conversation:job.target.conversation,fields:job.fields}),keepalive:true});
    result=await response.json();if(!response.ok||result.error)throw Error(result.error||'保存失败');
   }
   try{if(localStorage.getItem(draftKey(job.target))===JSON.stringify(job.fields))localStorage.removeItem(draftKey(job.target));}catch{}
   window.dispatchEvent(new CustomEvent('contact-profile-saved',{detail:{device:job.target.device,conversation:job.target.conversation}}));
   return result;
  });
  return saveQueue;
 }
 function flushPending(){
  if(timer!==null){clearTimeout(timer);timer=null;}
  if(!pending)return saveQueue;
  const job=pending;pending=null;
  return persist(job);
 }
 function scheduleSave(){
  if(!loaded||!currentTarget)return;
  const fields=readForm();pending={target:currentTarget,fields};
  try{localStorage.setItem(draftKey(currentTarget),JSON.stringify(fields));}catch{}
  if(timer!==null)clearTimeout(timer);
  timer=setTimeout(()=>{timer=null;flushPending().catch(reportSaveError);},400);
 }
 function controls(){
  const available=!!currentTarget&&loaded&&!(typeof workspaceBusy!=='undefined'&&workspaceBusy);
  for(const input of inputs)input.disabled=!available;
 }
 for(const input of inputs){input.disabled=true;input.addEventListener('input',scheduleSave);input.addEventListener('change',()=>{flushPending().catch(reportSaveError);});}
 async function refresh(){
  const target=context();if(target?.key===currentKey){controls();return;}
  const previousSave=flushPending();
  currentTarget=target;currentKey=target?.key||null;const ticket=++revision;loaded=false;writeForm({});controls();
  if(!target)return;
  try{
   await previousSave;
   let result;
   if(target.preview)result=JSON.parse(localStorage.getItem('iphone-contact-profile:'+target.key)||'{"fields":{}}');
   else{const response=await fetch('/api/contact-profile?'+new URLSearchParams({device:target.device,conversation:target.conversation}),{cache:'no-store'});result=await response.json();if(!response.ok||result.error)throw Error(result.error||'资料读取失败');}
   if(ticket!==revision)return;
   let localDraft=null;try{localDraft=JSON.parse(localStorage.getItem(draftKey(target))||'null');}catch{}
   writeForm(localDraft||result.fields||{});loaded=true;controls();
   if(localDraft){pending={target,fields:readForm()};timer=setTimeout(()=>{timer=null;flushPending().catch(reportSaveError);},100);}
  }catch(error){if(ticket===revision){currentTarget=null;loaded=false;controls();reportSaveError(error);}}
 }
 window.addEventListener('pagehide',()=>{flushPending().catch(reportSaveError);});
 window.refreshContactProfile=refresh;window.syncContactProfileControls=controls;
}
