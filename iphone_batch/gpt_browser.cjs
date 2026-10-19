/* Fill only the ChatGPT composer in a dedicated browser profile. Never submits. */
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function localJson(port,route,method='GET') {
 const response=await fetch('http://127.0.0.1:'+port+route,{method,signal:AbortSignal.timeout(2000)});
 if(!response.ok)throw Error('Browser connection unavailable');
 return response.json();
}
async function browserPort(profile) {
 try{
  const contents=await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8');
  const port=Number(contents.split('\n')[0]);
  if(!Number.isInteger(port)||port<1024||port>65535)return null;
  const version=await localJson(port,'/json/version');
  return version.webSocketDebuggerUrl?port:null;
 }catch{return null;}
}
async function ensureBrowser(profile,{headless=false}={}) {
 await fs.mkdir(profile,{recursive:true});
 const existing=await browserPort(profile);if(existing)return existing;
 const candidates=[
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google/Chrome/Application/chrome.exe'),
  path.join(process.env['PROGRAMFILES(X86)']||'C:\\Program Files (x86)','Microsoft/Edge/Application/msedge.exe')
 ];
 let executable=null;
 for(const candidate of candidates){try{await fs.access(candidate);executable=candidate;break;}catch{}}
 if(!executable)throw Error('需要安装 Chrome 或 Edge 浏览器');
 const args=['--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+profile,
  '--no-first-run','--no-default-browser-check','--new-window','about:blank'];
 if(headless)args.unshift('--headless=new','--disable-gpu');
 const child=spawn(executable,args,{detached:true,stdio:'ignore',windowsHide:headless});
 let spawnError=null;child.on('error',error=>{spawnError=error;});child.unref();
 const deadline=Date.now()+12000;
 while(Date.now()<deadline){if(spawnError)throw spawnError;const port=await browserPort(profile);if(port)return port;await delay(200);}
 throw Error('浏览器启动尚未完成，请稍后重试');
}

class CDP {
 constructor(socket){
  this.socket=socket;this.pending=new Map();this.sequence=0;
  socket.addEventListener('message',event=>{
   const message=JSON.parse(String(event.data));const pending=this.pending.get(message.id);
   if(!pending)return;this.pending.delete(message.id);clearTimeout(pending.timer);
   if(message.error)pending.reject(Error(message.error.message));else pending.resolve(message.result||{});
  });
  socket.addEventListener('close',()=>{
   for(const pending of this.pending.values()){clearTimeout(pending.timer);pending.reject(Error('Browser disconnected'));}
   this.pending.clear();
  });
 }
 static async connect(url){
  const parsed=new URL(url);
  if(parsed.protocol!=='ws:'||parsed.hostname!=='127.0.0.1')throw Error('Invalid local browser connection');
  const socket=new WebSocket(url);
  await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{socket.close();reject(Error('Browser connection timed out'));},5000);
   socket.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
   socket.addEventListener('error',()=>{clearTimeout(timer);reject(Error('Browser connection failed'));},{once:true});
  });
  return new CDP(socket);
 }
 call(method,params={}){
  const id=++this.sequence;
  return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{this.pending.delete(id);reject(Error('Browser command timed out'));},8000);
   this.pending.set(id,{resolve,reject,timer});this.socket.send(JSON.stringify({id,method,params}));
  });
 }
 async evaluate(expression){
  const response=await this.call('Runtime.evaluate',{expression,returnByValue:true});
  if(response.exceptionDetails)throw Error('Unable to inspect ChatGPT composer');
  return response.result?.value;
 }
 close(){this.socket.close();}
}

async function fillComposer(client,text,{origin='https://chatgpt.com',timeout=25000}={}) {
 const deadline=Date.now()+timeout;
 while(Date.now()<deadline){
  let state;
  try{state=await client.evaluate(`(()=>{
   if(location.origin!==${JSON.stringify(origin)})return 'waiting';
   const e=document.getElementById('prompt-textarea');
   if(!e||!(e.isContentEditable||e.tagName==='TEXTAREA')||e.disabled||!e.getClientRects().length)return 'waiting';
   if((e.value||e.innerText||'').trim())return 'existing_draft';
   e.focus();return document.activeElement===e?'ready':'waiting';
  })()`);}catch{state='waiting';}
  if(state==='existing_draft')return {status:'existing_draft'};
  if(state==='ready'){
   await client.call('Input.insertText',{text});
   const filled=await client.evaluate(`(()=>{
    if(location.origin!==${JSON.stringify(origin)})return null;
    const e=document.getElementById('prompt-textarea');return e?(e.value||e.innerText||''):null;
   })()`);
   return {status:typeof filled==='string'&&filled.replace(/\r/g,'').trimEnd()===text.replace(/\r/g,'').trimEnd()?'filled':'unverified'};
  }
  await delay(300);
 }
 return {status:'page_not_ready'};
}

async function openDraft(text,profile){
 const port=await ensureBrowser(profile);
 const target=await localJson(port,'/json/new?'+encodeURIComponent('https://chatgpt.com/'),'PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  await client.call('Page.bringToFront');
  return await fillComposer(client,text);
 }finally{client.close();}
}
module.exports={CDP,localJson,ensureBrowser,fillComposer,openDraft};
if(require.main===module){
 (async()=>{
  const chunks=[];for await(const chunk of process.stdin)chunks.push(chunk);
  const input=JSON.parse(Buffer.concat(chunks).toString('utf8'));
  if(typeof input.text!=='string'||!input.text.trim())throw Error('No conversation text');
  const result=await openDraft(input.text,path.resolve(__dirname,'.device-data/chatgpt-browser'));
  process.stdout.write(JSON.stringify(result));
 })().catch(()=>{process.stdout.write(JSON.stringify({status:'browser_error'}));process.exitCode=1;});
}
