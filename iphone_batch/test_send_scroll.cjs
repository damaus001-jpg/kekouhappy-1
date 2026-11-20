const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/send-scroll-'+process.pid),{headless:true});
 const target=await localJson(port,'/json/new?about:blank','PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  const html=fs.readFileSync(path.join(__dirname,'web/workspace.html'),'utf8');
  await client.evaluate(`document.body.innerHTML=${JSON.stringify(html.match(/<body[^>]*>([\s\S]*)<\/body>/i)[1].replace(/<script[\s\S]*?<\/script>/gi,''))};true`);
  const css=fs.readFileSync(path.join(__dirname,'web/dashboard.css'),'utf8');
  await client.evaluate(`const style=document.createElement('style');style.textContent=${JSON.stringify(css)};document.head.append(style);
   const fixture=document.createElement('style');fixture.textContent='body{margin:0;padding-top:1000px;padding-bottom:400px}main{height:600px!important;min-height:0!important}.work-panel{height:560px!important;min-height:0!important;overflow:auto!important}#messages{height:150px!important;min-height:150px!important;max-height:150px!important;flex:none!important;overflow:auto!important}.message{flex-shrink:0}';document.head.append(fixture);true`);
  const foreground=fs.readFileSync(path.join(__dirname,'web/foreground.js'),'utf8');
  const apply=foreground.slice(foreground.indexOf(' function applyForeground('),foreground.indexOf(' window.ForegroundSync=new'));
  await client.evaluate(fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8')+`
   const memory=new Map();Object.defineProperty(window,'localStorage',{value:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}});
   const active='D',number='+12025550123';workspaceDevice='D';window.ForegroundSync={number,activity(){}};
   const rows=Array.from({length:30},(_,i)=>({side:'incoming',kind:'text',text:'History '+i,time:'10:00'}));
   savedConversations=[{id:'old',phone_number:number,messages:rows}];currentConversationId='old';renderConversation();
   ${apply}
   true`);
  const response=await client.call('Runtime.evaluate',{awaitPromise:true,returnByValue:true,expression:`(async()=>{
   const settle=()=>new Promise(resolve=>setTimeout(resolve,250));
   window.scrollTo(0,document.documentElement.scrollHeight);await settle();
   const position=()=>({page:scrollY,phone:document.querySelector('.phone-panel').getBoundingClientRect().top});
   const before=position();messagesEl.scrollTop=0;
   applyForeground({phase:'send_acknowledged',receipt:{id:'sent',device:'D',number,text:'New message',baseline:outgoingBaseline('D',number)}});
   await settle();const acknowledged=position();
   const follows=messagesEl.scrollTop>0&&messagesEl.scrollHeight-messagesEl.clientHeight-messagesEl.scrollTop<2;
   const saved={id:'saved',phone_number:number,messages:[...rows,{side:'outgoing',kind:'text',text:'New message',time:'10:01',bubble_status:{delivery:'delivered'}}]};
   applyForeground({phase:'send_saved',phone_number:number,confirmed_receipt_id:'sent',conversations:[saved]});
   await settle();const confirmed=position();
   showSentReply({conversation:saved});await settle();
   return {before,acknowledged,confirmed,legacy:position(),follows};
  })()`});
  const result=response.result.value;assert.ok(result,JSON.stringify(response));
  assert.ok(result.before.page>0);assert.equal(result.follows,true);
  for(const phase of ['acknowledged','confirmed','legacy'])assert.deepEqual(result[phase],result.before,phase+' must preserve page and phone position');
  console.log('Send acknowledgement, confirmation and reply completion preserve page scroll and phone position; reading pane follows the new bubble.');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
