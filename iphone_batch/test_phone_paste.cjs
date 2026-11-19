const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/phone-paste-test'),{headless:true});
 const target=await localJson(port,'/json/new?about:blank','PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  const html=fs.readFileSync(path.join(__dirname,'web/workspace.html'),'utf8');
  const body=html.match(/<body[^>]*>([\s\S]*)<\/body>/i)[1].replace(/<script[\s\S]*?<\/script>/gi,'');
  await client.evaluate(`document.body.innerHTML=${JSON.stringify(body)};true`);
  const result=await client.evaluate(fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8')+`
   const memory=new Map();
   Object.defineProperty(window,'localStorage',{value:{getItem:k=>memory.get(k)||null,
    setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}});
   let watched=null;
   window.ForegroundSync={expectSend:(number,text)=>{watched={number,text};}};
   workspaceDevice='D';workspaceRevision=1;
   currentConversation={phone_number:'+12025550123',contact:'+12025550123'};
   function pending(text){return {id:'p',device:'D',revision:1,text,timer:null};}
   draftEl.value='Hello';localStorage.setItem(draftKey(),'Hello');phonePastePending=pending('Hello');
   finishPhonePaste('p',true);
   const success={value:draftEl.value,stored:localStorage.getItem(draftKey()),watched};
   draftEl.value='Retry';localStorage.setItem(draftKey(),'Retry');phonePastePending=pending('Retry');
   finishPhonePaste('p',false,'failed');
   const failed={value:draftEl.value,stored:localStorage.getItem(draftKey())};
   draftEl.value='New edit';localStorage.setItem(draftKey(),'New edit');phonePastePending=pending('Old text');
   finishPhonePaste('p',true);
   ({success,failed,edited:draftEl.value})
  `);
  assert.equal(result.success.value,'');assert.equal(result.success.stored,null);
  assert.deepEqual(result.success.watched,{number:'+12025550123',text:'Hello'});
  assert.deepEqual(result.failed,{value:'Retry',stored:'Retry'});
  assert.equal(result.edited,'New edit');
  console.log('Paste acknowledgement clears copied draft and cache; failures and later edits retain text');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
