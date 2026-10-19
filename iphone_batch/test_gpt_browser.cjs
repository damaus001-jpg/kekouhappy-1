const assert=require('node:assert/strict');
const {fillComposer,CDP,ensureBrowser,localJson}=require('./gpt_browser.cjs');
(async()=>{
 const calls=[];
 const sample='对方：Hello\n我方：你好\n🙂';
 let responses=['ready',sample];
 const client={evaluate:async()=>responses.shift(),call:async(method,params)=>calls.push({method,params})};
 assert.equal((await fillComposer(client,sample)).status,'filled');
 assert.deepEqual(calls,[{method:'Input.insertText',params:{text:sample}}]);
 responses=['existing_draft'];
 assert.equal((await fillComposer(client,sample)).status,'existing_draft');assert.equal(calls.length,1);
 responses=['ready','different'];
 assert.equal((await fillComposer(client,sample)).status,'unverified');assert.equal(calls.length,2);
 assert(calls.every(call=>call.method==='Input.insertText'));
 if(process.argv.includes('--integration')){
  const http=require('node:http'),path=require('node:path');
  const server=http.createServer((req,res)=>{
   res.setHeader('Content-Type','text/html; charset=utf-8');
   res.end('<!doctype html><form onsubmit="window.submitted=true;return false"><div id="prompt-textarea" contenteditable="true" style="width:400px;min-height:80px;white-space:pre-wrap"></div><button>Send</button></form>');
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let connection;
  try{
   const port=await ensureBrowser(path.join(__dirname,'.device-data/gpt-browser-test'),{headless:true});
   const origin='http://127.0.0.1:'+server.address().port;
   const target=await localJson(port,'/json/new?'+encodeURIComponent(origin),'PUT');
   connection=await CDP.connect(target.webSocketDebuggerUrl);
   assert.equal((await fillComposer(connection,sample,{origin,timeout:10000})).status,'filled');
   assert.equal(await connection.evaluate('Boolean(window.submitted)'),false);
   assert.equal((await fillComposer(connection,'Do not overwrite',{origin})).status,'existing_draft');
   await connection.call('Browser.close').catch(()=>{});
  }finally{connection?.close();await new Promise(resolve=>server.close(resolve));}
  console.log('Real Chromium composer passed: Unicode, multiline, exact fill, draft preservation, no submit');
 }
 console.log('GPT browser passed: fill-only commands, no send, existing drafts preserved and uncertain fills reported');
})().catch(error=>{console.error(error);process.exitCode=1;});
