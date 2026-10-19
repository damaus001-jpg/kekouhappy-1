const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/composer-test'),{headless:true});
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
   workspaceDevice='test-device';protectNotificationDraft=()=>{};window.replyCalls=[];
   workspaceRequest=async(action,data)=>{window.replyCalls.push(action);if(action==='draft')return {id:'test-draft',english:'Hello',sendable:true,phone_number:'+15550000001'};if(action==='send')return {conversation:{...currentConversation,messages:[...currentConversation.messages,{side:'outgoing',kind:'text',text:'Hello'}]}};throw Error('unexpected action');};
   draftEl.value='你好';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  `);
  await pause(100);
  assert.deepEqual(await client.evaluate('window.replyCalls'),['draft']);
  assert.equal(await client.evaluate('draftEl.value'),'Hello');
  await client.evaluate("draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))");
  await pause(100);
  assert.deepEqual(await client.evaluate('window.replyCalls'),['draft','send']);
  assert.equal(await client.evaluate('draftEl.value'),'');
  await client.evaluate(`
   window.replyCalls=[];draftEl.value='中文';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   for(const options of [{isComposing:true},{shiftKey:true},{repeat:true}])draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,...options}));
  `);
  await pause(50);assert.deepEqual(await client.evaluate('window.replyCalls'),[]);
  await client.evaluate(`
   workspaceRequest=async(action)=>{window.replyCalls.push(action);return {english:'残留中文',sendable:true};};
   draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  `);
  await pause(100);assert.deepEqual(await client.evaluate('window.replyCalls'),['draft']);
  assert.equal(await client.evaluate('draftEl.value'),'中文');
  await client.evaluate(`
   window.replyCalls=[];generatedDraft=null;draftEl.value='Hello again';draftEl.dispatchEvent(new Event('input',{bubbles:true}));
   workspaceRequest=async(action)=>{window.replyCalls.push(action);if(action==='direct_draft')return {id:'direct'};throw Error('send result unknown');};
   draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  `);
  await pause(100);await client.evaluate("draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))");
  await pause(50);assert.deepEqual(await client.evaluate('window.replyCalls'),['direct_draft','send']);
  await client.evaluate("draftEl.value='line\\n'.repeat(20);draftEl.dispatchEvent(new Event('input',{bubbles:true}))");
  assert.equal(await client.evaluate('draftEl.style.height'),'128px');
  console.log('Composer passed: real mouse emoji picker, cursor insertion, no bottom controls, in-place translation, second Enter sends once, Han/IME/repeat protection, no uncertain retry');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
