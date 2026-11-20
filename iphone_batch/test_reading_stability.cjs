const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/reading-stability-'+process.pid),{headless:true});
 const target=await localJson(port,'/json/new?about:blank','PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  const html=fs.readFileSync(path.join(__dirname,'web/workspace.html'),'utf8');
  await client.evaluate(`document.body.innerHTML=${JSON.stringify(html.match(/<body[^>]*>([\s\S]*)<\/body>/i)[1].replace(/<script[\s\S]*?<\/script>/gi,''))};true`);
  const foreground=fs.readFileSync(path.join(__dirname,'web/foreground.js'),'utf8');
  const apply=foreground.slice(foreground.indexOf(' function applyForeground('),foreground.indexOf(' window.ForegroundSync=new'));
  const result=await client.evaluate(fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8')+`
   const memory=new Map();Object.defineProperty(window,'localStorage',{value:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}});
   const active='D',number='+12086508575';workspaceDevice='D';window.ForegroundSync={number,activity(){}};
   const old={side:'outgoing',kind:'text',text:'Are you free tomorrow?',time:'2026-10-15T16:11:20+00:00',date_label:'Thu, Oct 15 at 9:11 AM',message_id:'db:55'};
   const rawOld={...old,time:'9:11 AM',message_id:undefined};
   const fresh={side:'outgoing',kind:'text',text:'Hey beautiful, what are you up to?',time:'6:12 PM'};
   savedConversations=[{id:'baseline',phone_number:number,messages:[old]}];currentConversationId='baseline';renderConversation();
   ${apply}
   const historyNode=document.querySelector('.message'),bodyNode=historyNode.querySelector('.original');
   const oldMeta=historyNode.querySelector('.message-meta').textContent;
   const range=document.createRange();range.setStart(bodyNode.firstChild,0);range.setEnd(bodyNode.firstChild,3);getSelection().removeAllRanges();getSelection().addRange(range);
   draftEl.value='Next draft';sendBlocked=true;
   applyForeground({phase:'send_acknowledged',phone_number:number,after_send:true,receipt:{id:'submit',device:'D',number,text:fresh.text,baseline:outgoingBaseline('D',number)}});
   const sentNode=document.querySelectorAll('.message')[1],counts=[document.querySelectorAll('.message').length];
   const progress=(revision,messages)=>applyForeground({phase:'reading_progress',progress:{device:'D',read_id:'read',revision,phone_number:number,contact:number,messages}});
   progress(1,[fresh]);counts.push(document.querySelectorAll('.message').length);
   progress(2,[{side:'unknown',text:old.text,kind:'text',reading_pending:true},fresh]);
   const knownSidePreserved=historyNode.classList.contains('outgoing')&&historyNode.querySelector('.message-meta').textContent===oldMeta;
   progress(2,[rawOld,{...fresh,date_label:'Today 6:12 PM'}]);counts.push(document.querySelectorAll('.message').length);
   progress(3,[rawOld]);counts.push(document.querySelectorAll('.message').length);
   const saved={id:'final',phone_number:number,messages:[old,{...fresh,date_label:'Today 6:12 PM',message_id:'ui:new',bubble_status:{delivery:'not_delivered'}}]};
   applyForeground({phase:'send_saved',phone_number:number,after_send:true,confirmed_receipt_id:'submit',conversations:[saved]});counts.push(document.querySelectorAll('.message').length);
   applyForeground({phase:'saved',phone_number:number,conversations:[{...saved,id:'same-content-new-file'}]});
   const stable={counts,knownSidePreserved,historySame:historyNode===document.querySelector('.message'),bodySame:bodyNode===document.querySelector('.original'),
    sentSame:sentNode===document.querySelectorAll('.message')[1],oldMetaSame:oldMeta===document.querySelector('.message-meta').textContent,
    selection:getSelection().toString(),draft:draftEl.value,status:document.querySelectorAll('.message')[1].querySelector('.message-status').textContent};
   window.ForegroundSync.number=null;applyForeground({phase:'identified',conversations:[]});
   const duringProbe=document.querySelectorAll('.message').length;
   window.ForegroundSync.number='+19999999999';applyForeground({phase:'identified',phone_number:'+19999999999',conversations:[{id:'other',phone_number:'+19999999999',messages:[{side:'incoming',text:'Different conversation',kind:'text'}]}]});
   ({stable,duringProbe,switched:Array.from(document.querySelectorAll('.original'),n=>n.textContent)})
  `);
  assert.deepEqual(result.stable.counts,[2,2,2,2,2]);
  assert.equal(result.stable.historySame,true);assert.equal(result.stable.bodySame,true);assert.equal(result.stable.sentSame,true);
  assert.equal(result.stable.knownSidePreserved,true);
  assert.equal(result.stable.oldMetaSame,true);assert.equal(result.stable.selection,'Are');
  assert.equal(result.stable.draft,'Next draft');assert.equal(result.stable.status,'未送达');
  assert.equal(result.duringProbe,2);assert.deepEqual(result.switched,['Different conversation']);
  const refreshResponse=await client.call('Runtime.evaluate',{expression:`(async()=>{
   const originalNode=document.querySelector('.message');let finish;
   globalThis.fetch=()=>new Promise(resolve=>{finish=resolve;});
   const loading=loadWorkspace('D',true);
   const historyVisible=originalNode===document.querySelector('.message');
   finish({ok:true,json:async()=>({conversations:[{id:'refreshed',phone_number:'+19999999999',messages:[{side:'incoming',text:'Different conversation',kind:'text'}]}]})});
   await loading;
   return {historyVisible,nodePreserved:originalNode===document.querySelector('.message'),text:document.querySelector('.original').textContent};
  })()`,awaitPromise:true,returnByValue:true});
  const refresh=refreshResponse.result.value;
  assert.deepEqual(refresh,{historyVisible:true,nodePreserved:true,text:'Different conversation'});
  console.log('History, bubble DOM, selected text and draft stay stable through pending/partial/final results; confirmed contact switch replaces the view');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
