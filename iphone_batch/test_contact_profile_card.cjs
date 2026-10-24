const assert=require('node:assert/strict'),path=require('node:path');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/contact-profile-test'),{headless:true});
 const target=await localJson(port,'/json/new?'+encodeURIComponent('http://127.0.0.1:8070/#preview-devices'),'PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 async function waitFor(expression){for(let i=0;i<100;i++){if(await client.evaluate(expression))return;await pause(50);}throw Error('Timeout: '+expression);}
 try{
  await client.call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await waitFor("document.querySelectorAll('.device-entry').length===20");
  await client.evaluate("localStorage.clear();document.querySelector('.device-entry').click();document.getElementById('profile-panel').open=true");
  await waitFor("!document.getElementById('profile-paste').disabled");
  await client.evaluate(`
   document.getElementById('profile-paste').value=JSON.stringify({'姓名':'Alice','年龄':'65','工作':'已退休','地区':'Dallas','婚否':'未提及','兴趣爱好':'园艺 🌹','其他信息':'','资料依据':'[1] I am retired.','待确认':'婚否尚未提及'});
   document.getElementById('apply-contact-profile').click();
  `);
  assert.equal(await client.evaluate("document.getElementById('contact-profile-field-2').value"),'已退休');
  assert.equal(await client.evaluate("document.getElementById('profile-state').textContent"),'未保存');
  await client.evaluate("document.getElementById('save-contact-profile').click()");
  await waitFor("document.getElementById('profile-state').textContent==='已保存'");
  // Different phone, same displayed contact number must not share the profile.
  await client.evaluate("document.querySelectorAll('.device-entry')[1].click()");
  await waitFor("!document.getElementById('profile-paste').disabled");
  assert.equal(await client.evaluate("document.getElementById('contact-profile-field-0').value"),'');
  await client.evaluate("document.querySelectorAll('.device-entry')[0].click()");
  await waitFor("document.getElementById('contact-profile-field-0').value==='Alice'");
  // Another contact on the same device starts empty; unsaved edits survive switching away.
  await client.evaluate("currentConversationId=savedConversations[1].id;renderConversation()");
  await waitFor("!document.getElementById('profile-paste').disabled");
  assert.equal(await client.evaluate("document.getElementById('contact-profile-field-0').value"),'');
  await client.evaluate("currentConversationId=savedConversations[0].id;renderConversation();document.getElementById('profile-panel').open=true");
  await waitFor("document.getElementById('contact-profile-field-0').value==='Alice'");
  await client.evaluate("document.getElementById('profile-paste').value='not valid JSON';document.getElementById('apply-contact-profile').click()");
  assert.equal(await client.evaluate("document.getElementById('contact-profile-field-0').value"),'Alice');
  // Full reload reads persisted preview data rather than an in-memory cache.
  await client.evaluate('location.reload()');await pause(250);
  await waitFor("document.querySelectorAll('.device-entry').length===20");
  await client.evaluate("document.querySelector('.device-entry').click();document.getElementById('profile-panel').open=true");
  await waitFor("document.getElementById('contact-profile-field-0').value==='Alice'");
  for(const width of [1440,820,600]){
   await client.call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await pause(100);
   const bounds=await client.evaluate("(()=>{const e=document.querySelector('.profile-body'),r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,overflow:e.scrollWidth>e.clientWidth};})()");
   assert(bounds.left>=0&&bounds.right<=width&&bounds.top>=0&&bounds.bottom<=900&&!bounds.overflow,JSON.stringify(bounds));
  }
  console.log('Contact card passed: import, edit-ready fields, save/reload, device and contact isolation, invalid JSON preserves data, three viewport sizes.');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
