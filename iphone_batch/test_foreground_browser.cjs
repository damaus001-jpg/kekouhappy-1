/* Full-page integration with simulated phones only. Never connects to USB. */
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function main(){
 const number='+12025550123';let selected='mock-one',version=1,ticks=0,pastes=[],sends=0,needsSave=true;
 const conversation=()=>({id:'mock-reading-'+version,phone_number:number,contact:number,scope:'模拟会话',
  messages:Array.from({length:90+version},(_,i)=>({side:i%2?'outgoing':'incoming',kind:'text',time:'10:00',text:'模拟消息 '+i}))});
 const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://127.0.0.1');
  const json=value=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));};
  if(url.searchParams.has('batch')){
   res.setHeader('Content-Type','text/html');res.end(`<canvas width="240" height="520" style="width:100%;height:100%;background:#314d3d"></canvas><script>
   window.addEventListener('message',async event=>{if(event.source!==parent||event.origin!==location.origin)return;
    if(event.data.type==='device-focus')parent.postMessage({type:'input-health-result',ready:true,state:'ready'},event.origin);
    if(event.data.type==='paste-composer'){
     await fetch('/mock/paste',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:event.data.text})});
     parent.postMessage({type:'paste-composer-result',id:event.data.id,ok:true},event.origin);
    }
    if(event.data.type==='monitor-snapshot')document.querySelector('canvas').toBlob(image=>parent.postMessage({type:'monitor-snapshot-result',id:event.data.id,image,state:'streaming'},event.origin),'image/jpeg');
   });</script>`);return;
  }
  let body={};if(req.method==='POST'){let raw='';for await(const chunk of req)raw+=chunk;body=JSON.parse(raw||'{}');}
  if(url.pathname==='/api/state')return json({active:selected,selected,scan_enabled:false,devices:[{udid:'mock-one',number:'18',name:'Simulated iPhone',port:server.address().port,ready:true,control_ready:true,enabled:true}]});
  if(url.pathname==='/api/cpu')return json({cpu_percent:32});
  if(url.pathname==='/api/messages')return json({conversations:[conversation()]});
  if(url.pathname==='/api/select'){selected=body.udid;return json({active:selected,selected,control_ready:true});}
  if(url.pathname==='/api/foreground'){
   if(body.action==='cancel')return json({phase:'cancelled'});
   ticks++;
   if(ticks===1)return json({phase:'identified',phone_number:number,conversations:[conversation()],next_seconds:.3});
   if(needsSave){needsSave=false;return json({phase:'saved',phone_number:number,conversations:[conversation()],next_seconds:.3});}
   return json({phase:'waiting',phone_number:number,next_seconds:.3});
  }
  if(url.pathname==='/mock/paste'){pastes.push(body.text);return json({ok:true});}
  if(url.pathname==='/api/workspace'){if(body.action==='send')sends++;return json({error:'No workspace action expected'});}
  if(url.pathname.startsWith('/api/'))return json({ok:true});
  const name=url.pathname==='/'?'workspace.html':url.pathname.slice(1);
  if(!/^[\w.-]+$/.test(name)){res.writeHead(404).end();return;}
  try{const data=await fs.readFile(path.join(__dirname,'web',name));res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');res.end(data);}
  catch{res.writeHead(404).end();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let client,browserPort,target;
 try{
  browserPort=await ensureBrowser(path.join(__dirname,'.device-data','foreground-browser-test'),{headless:true});
  target=await localJson(browserPort,'/json/new?about:blank','PUT');client=await CDP.connect(target.webSocketDebuggerUrl);
  const errors=[];
  client.socket.addEventListener('message',event=>{const data=JSON.parse(String(event.data));if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.exception?.description||data.params.exceptionDetails.text);});
  await client.call('Runtime.enable');await client.call('Page.enable');
  await client.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await client.call('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'});
  async function until(expression){const end=Date.now()+15000;while(Date.now()<end){if(await client.evaluate(expression))return;await delay(100);}throw Error('Timed out: '+expression);}
  await until("typeof ForegroundSyncController==='function'&&document.querySelectorAll('.device-entry').length===1");
  await client.evaluate("document.querySelector('main').scrollIntoView();");
  await until("window.ForegroundSync.number==='+12025550123'&&document.querySelectorAll('#messages .message').length===91");
  await until("cards.get('mock-one').inputReady===true");
  await client.evaluate("draftEl.value='中文 Hello 🌹';draftEl.dispatchEvent(new Event('input',{bubbles:true}));draftEl.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));");
  const pasteDeadline=Date.now()+5000;while(!pastes.length&&Date.now()<pasteDeadline)await delay(100);
  assert.deepEqual(pastes,['中文 Hello 🌹']);assert.equal(sends,0);
  assert.equal(await client.evaluate('draftEl.value'),'中文 Hello 🌹');
  await client.evaluate("draftEl.value='';draftEl.dispatchEvent(new Event('input',{bubbles:true}));messagesEl.scrollTop=100;");
  version=2;needsSave=true;
  await until("document.querySelectorAll('#messages .message').length===92");
  assert.equal(await client.evaluate('messagesEl.scrollTop'),100,'appended messages must not pull an older reading position to the bottom');
  await client.evaluate("cards.get('mock-one').frame.contentWindow.postMessage({type:'test-unused'},location.origin)");
  await client.evaluate("window.dispatchEvent(new MessageEvent('message',{source:cards.get('mock-one').frame.contentWindow,origin:cards.get('mock-one').origin,data:{type:'phone-activity',kind:'scroll'}}))");
  await until("window.ForegroundSync.historyPaused===true&&!document.getElementById('foreground-resume').hidden");
  const pausedTicks=ticks;await delay(2200);assert.equal(ticks,pausedTicks,'phone scroll must pause reading until explicitly resumed');
  await client.evaluate("document.getElementById('foreground-resume').click()");
  const resumeDeadline=Date.now()+5000;while(ticks===pausedTicks&&Date.now()<resumeDeadline)await delay(100);
  assert(ticks>pausedTicks);
  assert.equal(await client.evaluate("document.getElementById('screen-expand')"),null);
  assert.equal(await client.evaluate("document.getElementById('cpu-percent').textContent"),'32%');
  assert.deepEqual(errors,[]);
  const screenshot=await client.call('Page.captureScreenshot',{format:'png'});
  const screenshotPath=path.join(__dirname,'.device-data','diagnostics','foreground-browser-test.png');
  await fs.mkdir(path.dirname(screenshotPath),{recursive:true});await fs.writeFile(screenshotPath,Buffer.from(screenshot.data,'base64'));
  console.log('Full browser passed: identify/cache, automatic update, Enter pastes exact text without sending, draft retained, reading position preserved, phone-scroll pause/resume, CPU bar, no page exceptions. Screenshot: '+screenshotPath);
 }finally{
  if(client)client.socket.close();
  if(browserPort&&target)await localJson(browserPort,'/json/close/'+target.id).catch(()=>{});
  server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
