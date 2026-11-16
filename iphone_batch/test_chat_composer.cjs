const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const port=await ensureBrowser(process.env.IPHONE_BATCH_TEST_BROWSER_PROFILE||path.join(__dirname,'.device-data/composer-test'),{headless:true});
 const target=await localJson(port,'/json/new?'+encodeURIComponent('http://127.0.0.1:8070/#preview-devices'),'PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 async function click(selector){
  const point=await client.evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  await client.call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
  await client.call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
 }
 try{
  await client.call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  for(let i=0;i<50;i++){if(await client.evaluate("document.querySelectorAll('.device-entry').length===20"))break;await pause(100);}
  await click('#toggle-emoji');
  const before=await client.evaluate(`(()=>{const e=document.getElementById('emoji-picker'),r=e.getBoundingClientRect();return {hidden:e.hidden,count:e.children.length,left:r.left,right:r.right,top:r.top,bottom:r.bottom};})()`);
  assert(!before.hidden&&before.count>=40,JSON.stringify(before));
  assert(before.left>=0&&before.right<=1440&&before.top>=0&&before.bottom<=900,JSON.stringify(before));
  await click('#emoji-picker button[data-emoji="🌹"]');
  assert.equal(await client.evaluate('draftEl.value'),'🌹');
  assert.equal(await client.evaluate("document.getElementById('send-reply').disabled"),true);
  await client.evaluate("document.querySelector('.device-entry').click();draftEl.value='Hi there';draftEl.setSelectionRange(3,3);draftEl.dispatchEvent(new Event('input',{bubbles:true}))");
  await click('#toggle-emoji');await click('#emoji-picker button');
  assert.equal(await client.evaluate('draftEl.value'),'Hi 😀there');
  assert.equal(await client.evaluate("document.getElementById('emoji-picker').hidden"),true);
  await click('#toggle-emoji');await click('#emoji-picker button[data-emoji="💐"]');
  assert((await client.evaluate('draftEl.value')).includes('💐'));
  assert.equal(await client.evaluate("document.querySelector('.chat-compose-row').nextElementSibling===null"),true);
  await client.evaluate(`
   window.originalWorkspaceRequest=workspaceRequest;
   workspaceDevice='test-device';controlOwner='test-device';protectNotificationDraft=()=>{};
   window.replyCalls=[];window.rawTexts=[];
   workspaceRequest=async(action,data)=>{window.replyCalls.push(action);
    if(action==='direct_draft'){rawTexts.push(data.text);return {id:'raw-draft'};}
    if(action==='send')return {conversation:{...currentConversation,messages:[...currentConversation.messages,{side:'outgoing',kind:'text',text:rawTexts.at(-1)}]}};
    throw Error('unexpected action');
   };
  `);
  for(const text of ['你好','Hello','中文 English 🌹','  保留空格  ']){
   await client.evaluate(`sendBlocked=false;draftEl.value=${JSON.stringify(text)};draftEl.dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('send-reply').click();document.getElementById('send-reply').click();`);
   await pause(60);
   assert.equal(await client.evaluate('rawTexts.at(-1)'),text);
   assert.equal(await client.evaluate('draftEl.value'),'');
  }
  assert.deepEqual(await client.evaluate('window.replyCalls'),Array(4).fill(['direct_draft','send']).flat());
  assert.equal(await client.evaluate("document.querySelectorAll('.message-retranslate,.translated').length"),0);
  await client.evaluate(`
   window.replyCalls=[];sendBlocked=false;draftEl.value='中文';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   for(const options of [{isComposing:true},{shiftKey:true},{repeat:true}])draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,...options}));
  `);
  await pause(50);assert.deepEqual(await client.evaluate('window.replyCalls'),[]);
  await client.evaluate(`
   window.replyCalls=[];generatedDraft=null;sendBlocked=false;
   cards.set('test-device',{inputReady:false});
   draftEl.value='OK';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  `);
  await pause(50);assert.deepEqual(await client.evaluate('window.replyCalls'),[]);
  assert.equal(await client.evaluate('draftEl.value'),'OK');
  assert.equal(await client.evaluate("document.getElementById('send-reply').disabled"),true);
  assert.match(await client.evaluate("document.getElementById('archive-status').textContent"),/控制连接不可用/);
  await client.evaluate("cards.delete('test-device')");
  await client.evaluate(`
   window.originalFetch=fetch;window.replyCalls=[];window.sendAttempts=0;
   workspaceRequest=window.originalWorkspaceRequest;
   window.fetch=async(url,options)=>{
    const body=JSON.parse(options.body);replyCalls.push(body.action);
    if(body.action==='direct_draft')return {ok:true,json:async()=>({id:'manual-draft'})};
    if(++sendAttempts===1)return {ok:false,json:async()=>({error:'未定位到唯一可用的手机发送按钮，未执行发送'})};
    return {ok:true,json:async()=>({status:'sent_verified'})};
   };
   generatedDraft=null;sendBlocked=false;draftEl.value='ok';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   document.getElementById('send-reply').click();
  `);
  await pause(100);
  assert.deepEqual(await client.evaluate('window.replyCalls'),['direct_draft','send']);
  assert.equal(await client.evaluate('sendBlocked'),false);
  assert.equal(await client.evaluate('draftEl.value'),'ok');
  await pause(100);assert.equal(await client.evaluate('sendAttempts'),1,'a proven pre-send failure never retries itself');
  await client.evaluate("document.getElementById('send-reply').click()");
  await pause(100);
  assert.deepEqual(await client.evaluate('window.replyCalls'),['direct_draft','send','direct_draft','send']);
  assert.equal(await client.evaluate('draftEl.value'),'');
  await client.evaluate('window.fetch=window.originalFetch;sendBlocked=false');
  await client.evaluate(`
   window.replyCalls=[];generatedDraft=null;draftEl.value='Hello again';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   workspaceRequest=async(action)=>{window.replyCalls.push(action);if(action==='direct_draft')return {id:'direct'};throw Error('send result unknown');};
   document.getElementById('send-reply').click();
  `);
  await pause(100);await client.evaluate("document.getElementById('send-reply').click()");
  await pause(50);assert.deepEqual(await client.evaluate('window.replyCalls'),['direct_draft','send']);
  await client.evaluate("draftEl.value='line\\n'.repeat(20);draftEl.dispatchEvent(new Event('input',{bubbles:true}))");
  assert.equal(await client.evaluate('draftEl.style.height'),'128px');
  console.log('Composer passed: real mouse emoji picker, cursor insertion, explicit Send button sends once, no translation UI, IME/repeat protection, no uncertain retry');
 }finally{client.close();await localJson(port,'/json/close/'+target.id).catch(()=>{});}
})().catch(error=>{console.error(error);process.exitCode=1;});
