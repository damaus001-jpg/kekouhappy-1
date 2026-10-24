const CONTACT_PROFILE_FIELDS=['姓名','年龄','工作','地区','婚否','兴趣爱好','其他信息','资料依据','待确认'];
function parseContactProfile(text){
 if(typeof text!=='string'||text.length>50000)throw Error('请粘贴完整的 GPT 资料结果，最多 50000 字。');
 const cleaned=text.trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'');
 let value;try{value=JSON.parse(cleaned);}catch{throw Error('请复制 GPT 输出的完整 JSON 资料，包括开头和结尾的大括号。');}
 if(!value||Array.isArray(value)||typeof value!=='object'||!CONTACT_PROFILE_FIELDS.some(key=>Object.hasOwn(value,key)))throw Error('没有找到姓名、年龄等联系人资料字段。');
 const fields={};
 for(const key of CONTACT_PROFILE_FIELDS){
  if(!Object.hasOwn(value,key))continue;
  if(typeof value[key]!=='string'||value[key].length>(CONTACT_PROFILE_FIELDS.indexOf(key)<6?1000:8000))throw Error(key+'应为文字，且不能过长。');
  fields[key]=value[key].trim();
 }
 return fields;
}
if(typeof module!=='undefined'&&module.exports)module.exports={CONTACT_PROFILE_FIELDS,parseContactProfile};

if(typeof document!=='undefined'){
 const inputs=new Map(),drafts=new Map();let currentKey=null,revision=0,loaded=false,saving=false;
 const grid=document.getElementById('contact-profile-fields'),paste=document.getElementById('profile-paste');
 const save=document.getElementById('save-contact-profile'),apply=document.getElementById('apply-contact-profile');
 const state=document.getElementById('profile-state'),feedback=document.getElementById('profile-feedback');
 for(const [index,name] of CONTACT_PROFILE_FIELDS.entries()){
  const label=document.createElement('label');label.textContent=name;
  const input=document.createElement(index<6?'input':'textarea');input.id='contact-profile-field-'+index;input.maxLength=index<6?1000:8000;input.disabled=true;
  if(index>=6){input.rows=2;label.className='profile-wide';}else input.type='text';
  input.placeholder=index===2?'在职、职业或已退休':index===3?'现居地 / 家乡':'未提及';
  label.append(input);grid.append(label);inputs.set(name,input);
  input.addEventListener('input',()=>{if(currentKey){drafts.set(currentKey,readForm());state.textContent='未保存';}});
 }
 function context(){
  if(typeof currentConversation==='undefined'||!currentConversation)return null;
  const preview=typeof devicePreview!=='undefined'&&devicePreview;
  const device=preview?previewLoadedDevice:workspaceDevice;if(!device)return null;
  const raw=currentConversation.phone_number||currentConversation.contact||'',digits=raw.replace(/\D/g,'');
  const phone=/^\+?[\d ()-]+$/.test(raw)?(raw.startsWith('+')&&digits.length>=7&&digits.length<=15?'+'+digits:digits.length===10?'+1'+digits:digits.length===11&&digits.startsWith('1')?'+'+digits:null):null;
  return {device,preview,conversation:currentConversation.id,key:(preview?'preview:':'device:')+device+':'+(phone||currentConversation.id),label:raw};
 }
 function readForm(){return Object.fromEntries([...inputs].map(([key,input])=>[key,input.value]));}
 function writeForm(fields){for(const [key,input] of inputs)input.value=fields[key]||'';}
 function controls(){
  const available=!!context()&&loaded&&!saving&&!(typeof workspaceBusy!=='undefined'&&workspaceBusy);
  for(const input of inputs.values())input.disabled=!available;
  save.disabled=apply.disabled=paste.disabled=!available;
 }
 async function refresh(){
  const target=context();if(target?.key===currentKey){controls();return;}
  currentKey=target?.key||null;const ticket=++revision;loaded=false;writeForm({});paste.value='';feedback.textContent='';
  document.getElementById('profile-contact').textContent=target?'对方：'+target.label:'先读取联系人会话';
  state.textContent=target?'读取中':'待填写';controls();if(!target)return;
  try{
   let result;
   if(target.preview)result=JSON.parse(localStorage.getItem('iphone-contact-profile:'+target.key)||'{"fields":{}}');
   else{const response=await fetch('/api/contact-profile?'+new URLSearchParams({device:target.device,conversation:target.conversation}),{cache:'no-store'});result=await response.json();if(!response.ok||result.error)throw Error(result.error||'资料读取失败');}
   if(ticket!==revision)return;
   writeForm(drafts.get(target.key)||result.fields||{});loaded=true;
   state.textContent=drafts.has(target.key)?'未保存':result.updated?'已保存':'待填写';
  }catch{if(ticket===revision){state.textContent='读取失败';feedback.textContent='资料读取失败，请点击刷新已保存记录后重试。';currentKey=null;}}
  finally{if(ticket===revision)controls();}
 }
 apply.addEventListener('click',()=>{
  if(!currentKey||apply.disabled)return;
  try{const fields=parseContactProfile(paste.value);for(const [key,value] of Object.entries(fields))inputs.get(key).value=value;drafts.set(currentKey,readForm());state.textContent='未保存';feedback.textContent='已填入，请检查后保存。';paste.value='';}
  catch(error){feedback.textContent=error.message;}
 });
 save.addEventListener('click',async()=>{
  const target=context();if(!target||save.disabled)return;
  const fields=readForm(),ticket=revision;saving=true;controls();feedback.textContent='正在保存…';
  try{
   let result;
   if(target.preview){result={fields,updated:new Date().toISOString()};localStorage.setItem('iphone-contact-profile:'+target.key,JSON.stringify(result));}
   else{const response=await fetch('/api/contact-profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:target.device,conversation:target.conversation,fields})});result=await response.json();if(!response.ok||result.error)throw Error(result.error||'保存失败');}
   drafts.delete(target.key);
   if(ticket===revision){state.textContent='已保存';feedback.textContent='已保存到此联系人的资料卡片。';}
  }catch(error){if(ticket===revision){state.textContent='未保存';feedback.textContent=error.message;}}
  finally{saving=false;controls();}
 });
 window.addEventListener('beforeunload',event=>{if(drafts.size){event.preventDefault();event.returnValue='';}});
 window.refreshContactProfile=refresh;window.syncContactProfileControls=controls;
}
