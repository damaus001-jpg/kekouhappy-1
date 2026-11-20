const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/outgoing-receipts-test-'+process.pid),{headless:true});
 const target=await localJson(port,'/json/new?about:blank','PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  const html=fs.readFileSync(path.join(__dirname,'web/workspace.html'),'utf8');
  await client.evaluate(`document.body.innerHTML=${JSON.stringify(html.match(/<body[^>]*>([\s\S]*)<\/body>/i)[1].replace(/<script[\s\S]*?<\/script>/gi,''))};true`);
  const foreground=fs.readFileSync(path.join(__dirname,'web/foreground.js'),'utf8');
  const apply=foreground.slice(foreground.indexOf(' function applyForeground('),foreground.indexOf(' window.ForegroundSync=new'));
  const result=await client.evaluate(fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8')+`
   const memory=new Map();Object.defineProperty(window,'localStorage',{value:{getItem:k=>memory.get(k)||null,
    setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}});
   const active='D',number='+12025550123';workspaceDevice='D';
   window.ForegroundSync={number,activity(){}};
   const old={side:'outgoing',text:'Same',time:'10:00',kind:'text'};
   savedConversations=[{id:'old',phone_number:number,messages:[old]}];currentConversationId='old';renderConversation();
   ${apply}
   const baseline=outgoingBaseline('D',number);
   const ack=id=>applyForeground({phase:'send_acknowledged',phone_number:number,after_send:true,
    receipt:{id,device:'D',number,text:'Same',baseline}});
   draftEl.value='Next draft';sendBlocked=true;
   ack('A');ack('A');
   const first={count:document.querySelectorAll('.message').length,
    status:document.querySelector('.message:last-child .message-status').textContent,draft:draftEl.value,blocked:sendBlocked};
   ack('B');
   const afterOne={id:'one',phone_number:number,messages:[old,{...old,time:'10:01',bubble_status:{delivery:'not_delivered'}}]};
   applyForeground({phase:'send_saved',phone_number:number,after_send:true,confirmed_receipt_id:'A',conversations:[afterOne]});
   const partial={count:document.querySelectorAll('.message').length,
    pending:outgoingReceipts('D',number).map(r=>r.id),draft:draftEl.value};
   const afterBoth={id:'two',phone_number:number,messages:[...afterOne.messages,{...old,time:'10:02',bubble_status:{delivery:'delivered'}}]};
   applyForeground({phase:'send_saved',phone_number:number,after_send:true,confirmed_receipt_id:'B',conversations:[afterBoth]});
   const final={count:document.querySelectorAll('.message').length,
     pending:outgoingReceipts('D',number).length,statuses:Array.from(document.querySelectorAll('.message-status'),n=>n.textContent),draft:draftEl.value};
   const beforeProgress=workspaceRevision;
   applyForeground({phase:'reading_progress',progress:{device:'D',read_id:'r',phone_number:number,contact:number,
    messages:[{side:'unknown',text:'Recognized now',kind:'text',reading_pending:true}]}});
   const live={count:document.querySelectorAll('.message').length,text:document.querySelector('.message:last-child .original').textContent,
    status:document.querySelector('.message:last-child .message-status').textContent,draft:draftEl.value,revisionUnchanged:beforeProgress===workspaceRevision};
   applyForeground({phase:'saved',phone_number:number,conversations:[afterBoth]});
   ({first,partial,final,live,finished:{count:document.querySelectorAll('.message').length,draft:draftEl.value,reading:!!currentConversation.ui_reading}})
  `);
  assert.deepEqual(result.first,{count:2,status:'已提交，待核对',draft:'Next draft',blocked:true});
  assert.deepEqual(result.partial,{count:3,pending:['B'],draft:'Next draft'});
  assert.deepEqual(result.final,{count:3,pending:0,statuses:['未送达','已送达'],draft:'Next draft'});
  assert.deepEqual(result.live,{count:4,text:'Recognized now',status:'字段待核对',draft:'Next draft',revisionUnchanged:true});
  assert.deepEqual(result.finished,{count:4,draft:'Next draft',reading:false});
  console.log('Browser: immediate pending bubble, duplicate ack guard, next draft preserved, repeated sends reconcile once with native statuses');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
