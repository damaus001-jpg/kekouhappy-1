const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/followup-selection-'+process.pid),{headless:true});
 const target=await localJson(port,'/json/new?about:blank','PUT'),client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  const source=fs.readFileSync(path.join(__dirname,'web/dashboard.js'),'utf8');
  const code=source.slice(source.indexOf('function followupTextSelected('),source.indexOf('async function openFollowupContact('));
  await client.evaluate(`document.body.innerHTML='<span id="followup-contact-count"></span><div id="followup-contact-list" class="followup-contact-list"></div>';document.head.innerHTML='<style>'+${JSON.stringify(fs.readFileSync(path.join(__dirname,'web/dashboard.css'),'utf8'))}+'</style>';
   let followupRenderRevision=0,workspaceBusy=false;const active='D',latest=[{udid:'D'}],opened=[];
   const contactFollowups=()=>({'phone:12025550123':true}),isContactFollowup=()=>true;
   const followupProfile=()=>Promise.resolve({'日期':'2026-11-19','姓名':'Alice','爱好':'Swimming'});
   function positionReadingCards(){}function openFollowupContact(device,number){opened.push({device,number});}
   ${code}renderFollowupContacts();true`);
  await new Promise(r=>setTimeout(r,100));
  const bounds=await client.evaluate(`(()=>{const e=document.querySelector('.followup-contact'),r=document.createRange();r.selectNodeContents(e);const b=r.getBoundingClientRect();return {left:b.left,top:b.top,right:b.right,height:b.height,text:e.textContent,select:getComputedStyle(e).userSelect}})()`);
  assert.equal(bounds.select,'text');assert(bounds.text.includes('2026-11-19')&&bounds.text.includes('Swimming'));
  const y=bounds.top+bounds.height/2;
  await client.call('Input.dispatchMouseEvent',{type:'mousePressed',x:bounds.left+1,y,button:'left',clickCount:1});
  for(let i=1;i<=8;i++)await client.call('Input.dispatchMouseEvent',{type:'mouseMoved',x:bounds.left+(bounds.right-bounds.left+2)*i/8,y,button:'left',buttons:1});
  await client.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:bounds.right+2,y,button:'left',clickCount:1});
  const selection=await client.evaluate(`(()=>{const before=getSelection().toString(),row=document.querySelector('.followup-contact');renderFollowupContacts();return {before,after:getSelection().toString(),opens:opened.length,same:row===document.querySelector('.followup-contact')}})()`);
  assert(selection.before.includes('12025550123')&&selection.before.includes('2026-11-19')&&selection.before.includes('Swimming'));
  assert.equal(selection.before,selection.after);assert.equal(selection.opens,0);assert.equal(selection.same,true);
  await client.evaluate('getSelection().removeAllRanges();true');
  await client.call('Input.dispatchMouseEvent',{type:'mousePressed',x:bounds.left+10,y,button:'left',clickCount:1});
  await client.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:bounds.left+10,y,button:'left',clickCount:1});
  assert.equal(await client.evaluate('opened.length'),1);
  console.log('Follow-up text drag selects number/date/hobby without opening; selection survives refresh; plain click still opens');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
