/* Browser verification against simulated phones; --live only observes thumbnails. */
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const web=path.join(__dirname,'web');
async function until(client,expression,timeout=15000){
 const end=Date.now()+timeout;while(Date.now()<end){if(await client.evaluate(expression))return;await delay(150);}throw Error('Timed out: '+expression);
}
async function main(){
 const live=process.argv.includes('--live'),metadataOnly=process.argv.includes('--metadata-only');let selected=null,server=null,port=8070;
 const modes=new Map(),reconnectJobs=new Map();
 if(!live){
  server=http.createServer(async(req,res)=>{
   const url=new URL(req.url,'http://127.0.0.1');
   const json=value=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));};
   if(url.searchParams.has('batch')){
    res.setHeader('Content-Type','text/html');res.end(`<canvas width="240" height="520"></canvas><script>
    const c=document.querySelector('canvas'),ctx=c.getContext('2d');let tick=0;
    window.addEventListener('message',e=>{if(e.source!==parent||e.origin!==location.origin)return;
    if(e.data.type==='monitor-snapshot'){ctx.fillStyle='hsl('+((++tick*39)%360)+' 35% 25%)';ctx.fillRect(0,0,240,520);ctx.fillStyle='#fff';ctx.font='24px sans-serif';ctx.fillText('Phone '+tick,24,65);c.toBlob(image=>parent.postMessage({type:'monitor-snapshot-result',id:e.data.id,image,state:'streaming'},e.origin),'image/jpeg');}});
    </script>`);return;
   }
   if(url.pathname==='/api/cpu')return json({cpu_percent:35});
   if(url.pathname==='/api/state')return json({active:selected,selected,scan_enabled:false,devices:Array.from({length:20},(_,i)=>{
    const mode=modes.get('mock-'+i)||{enabled:true,readonly:false},job=reconnectJobs.get('mock-'+i)||{};
    return {udid:'mock-'+i,name:'iPhone '+(i+1),number:String(i+1).padStart(2,'0'),port,...mode,...job,
     ready:mode.enabled&&!job.reconnecting,control_ready:mode.enabled&&!mode.readonly&&!job.reconnecting,error:mode.enabled?null:'已手动断开，画面与操作均已关闭'};
   })});
   if(url.pathname==='/api/devices/reconnect'){
    let body='';for await(const part of req)body+=part;const {device}=JSON.parse(body),job='reconnect-'+device;
    reconnectJobs.set(device,{reconnecting:true,reconnect_id:job,reconnect_state:'reconnecting',reconnect_stage:'trusting',reconnect_elapsed:0});
    setTimeout(()=>reconnectJobs.set(device,{reconnecting:false,reconnect_id:job,reconnect_state:'ready',reconnect_stage:'ready',reconnect_elapsed:1.2}),1200);
    return json({ok:true,job});
   }
   if(url.pathname==='/api/devices/access'){
    let body='';for await(const part of req)body+=part;const value=JSON.parse(body),mode={enabled:true,readonly:false,...modes.get(value.device)};
    for(const key of ['enabled','readonly'])if(typeof value[key]==='boolean')mode[key]=value[key];
    modes.set(value.device,mode);if(!mode.enabled||mode.readonly){if(selected===value.device)selected=null;}
    return json({ok:true,...mode,message:'模拟设备模式已更新'});
   }
   if(url.pathname==='/api/select'){
    let body='';for await(const part of req)body+=part;selected=JSON.parse(body).udid;return json({active:selected,selected,control_ready:true});
   }
   if(url.pathname==='/api/messages')return json({conversations:[]});
   if(url.pathname.startsWith('/api/'))return json({ok:true});
   const name=url.pathname==='/'?'workspace.html':url.pathname.slice(1);
   if(!/^[\w.-]+$/.test(name)){res.writeHead(404).end();return;}
   try{const bytes=await fs.readFile(path.join(web,name));res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');res.end(bytes);}catch{res.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));port=server.address().port;
 }
 const profile=path.join(__dirname,'.device-data','monitor-browser-test-'+process.pid);
 let client,browserPort;
 try{
  browserPort=await ensureBrowser(profile,{headless:true});
  const target=await localJson(browserPort,'/json/new?about:blank','PUT');client=await CDP.connect(target.webSocketDebuggerUrl);
  const errors=[],videoContexts=new Set();
  client.socket.addEventListener('message',event=>{
   const data=JSON.parse(String(event.data));
   if(data.method==='Runtime.executionContextCreated'&&data.params.context.auxData?.isDefault)videoContexts.add(data.params.context.id);
   if(data.method==='Runtime.executionContextDestroyed')videoContexts.delete(data.params.executionContextId);
  });
  client.socket.addEventListener('message',event=>{const data=JSON.parse(String(event.data));if(data.method==='Runtime.exceptionThrown')errors.push(metadataOnly?'runtime-exception':data.params.exceptionDetails.exception?.description||data.params.exceptionDetails.text);});
  await client.call('Runtime.enable');await client.call('Page.enable');
  await client.call('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
  if(live){
   const key=Buffer.from((await fs.readFile(path.join(process.env.LOCALAPPDATA,'PikachuSmsBridge/workspace-access.key'),'ascii')).trim(),'hex');
   client.socket.addEventListener('message',event=>{
    const data=JSON.parse(String(event.data));if(data.method!=='Fetch.requestPaused')return;
    const {requestId,request}=data.params,url=new URL(request.url);
    // Observe live video only: never select a phone, send keys or submit SMS.
    const allowedPost=url.pathname==='/pli'||(!metadataOnly&&url.pathname==='/input-health');
    if(request.method!=='GET'&&!(request.method==='POST'&&allowedPost)){
     void client.call('Fetch.failRequest',{requestId,errorReason:'Aborted'}).catch(()=>{});return;
    }
    const timestamp=String(Math.floor(Date.now()/1000)),nonce=crypto.randomBytes(16).toString('hex');
    const text=['v1',request.method.toUpperCase(),url.port||'80',url.pathname+url.search,timestamp,nonce].join('\n');
    const digest=crypto.createHmac('sha256',key).update(text).digest('hex');
    const headers=Object.entries(request.headers).filter(([name])=>name.toLowerCase()!=='x-pikachu-workspace-auth').map(([name,value])=>({name,value:String(value)}));
    headers.push({name:'X-Pikachu-Workspace-Auth',value:`v1:${timestamp}:${nonce}:${digest}`});
    void client.call('Fetch.continueRequest',{requestId,headers}).catch(()=>{});
   });
   await client.call('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:*/*',requestStage:'Request'}]});
  }
  await client.call('Page.navigate',{url:'http://127.0.0.1:'+port+'/'});
  await until(client,"document.querySelectorAll('.monitor-tile').length>0");
  await until(client,"document.querySelectorAll('.monitor-screen img:not([hidden])').length>0",live?30000:15000);
  if(live&&metadataOnly){
   for(let sample=0;sample<4;sample++){
    const metrics=[];
    for(const contextId of videoContexts){
     try{
      const value=await client.call('Runtime.evaluate',{contextId,expression:'typeof window.videoHealth === "function" ? window.videoHealth() : null',returnByValue:true});
      if(value.result.value)metrics.push(value.result.value);
     }catch{}
    }
    console.log(JSON.stringify({sample,at:new Date().toISOString(),video:metrics}));
    if(sample<3)await delay(5000);
   }
  }
  if(!live){
   await until(client,"document.querySelectorAll('.monitor-screen img:not([hidden])').length===20");
   const geometry=await client.evaluate(`(()=>{const tiles=[...document.querySelectorAll('.monitor-tile')].map(e=>e.getBoundingClientRect()),main=document.querySelector('main').getBoundingClientRect(),wall=document.getElementById('global-monitor').getBoundingClientRect();return {count:tiles.length,columns:tiles.filter(r=>Math.abs(r.top-tiles[0].top)<1).length,below:main.top>=wall.bottom-1,overflow:document.documentElement.scrollWidth>innerWidth};})()`);
   assert.deepEqual(geometry,{count:20,columns:10,below:true,overflow:false});
   assert(await client.evaluate("document.querySelectorAll('.monitor-state,.monitor-followup').length===0&&document.querySelector('.monitor-header #monitor-notice')!==null"));
   await client.evaluate("window.layoutFrames=[...document.querySelectorAll('#selected iframe')];document.getElementById('monitor-layout').click()");
   const single=await client.evaluate(`(()=>{const g=document.getElementById('monitor-grid'),r=g.getBoundingClientRect(),tiles=[...g.children].map(e=>e.getBoundingClientRect());return {mode:document.getElementById('global-monitor').dataset.layout,rows:new Set(tiles.map(t=>Math.round(t.top))).size,visible:tiles.filter(t=>t.left>=r.left-1&&t.right<=r.right+1).length,overflow:g.scrollWidth>g.clientWidth,same:layoutFrames.every((frame,i)=>frame===document.querySelectorAll('#selected iframe')[i])};})()`);
   assert.deepEqual(single,{mode:'single',rows:1,visible:5,overflow:true,same:true});
   await client.evaluate("document.getElementById('monitor-layout').click()");
   assert(await client.evaluate("document.getElementById('global-monitor').dataset.layout==='double'&&localStorage.getItem('monitor-layout')==='double'&&layoutFrames.every((frame,i)=>frame===document.querySelectorAll('#selected iframe')[i])"));
   await client.evaluate("document.getElementById('monitor-size').value='240';document.getElementById('monitor-size').dispatchEvent(new Event('input'));document.getElementById('monitor-layout').click();document.getElementById('monitor-size').value='360';document.getElementById('monitor-size').dispatchEvent(new Event('input'))");
   assert(await client.evaluate("Math.abs(document.querySelector('.monitor-tile').getBoundingClientRect().width-360)<1&&document.getElementById('monitor-size-value').textContent==='360 px'"));
   await client.evaluate("document.getElementById('monitor-layout').click()");
   assert(await client.evaluate(`(()=>{const grid=document.getElementById('monitor-grid'),tiles=[...document.querySelectorAll('.monitor-tile')].map(e=>e.getBoundingClientRect()),top=tiles.filter(t=>Math.abs(t.top-tiles[0].top)<1),visible=top.filter(t=>t.left>=grid.getBoundingClientRect().left-1&&t.right<=grid.getBoundingClientRect().right+1);return visible.length!==10&&Math.abs(visible.at(-1).right-grid.getBoundingClientRect().right)<1&&new Set(tiles.map(t=>Math.round(t.top))).size===2&&document.getElementById('monitor-size').value==='240'&&localStorage.getItem('monitor-size-single')==='360'&&localStorage.getItem('monitor-size-double')==='240'&&layoutFrames.every((frame,i)=>frame===document.querySelectorAll('#selected iframe')[i])&&!document.querySelector('aside.devices')&&document.getElementById('device-list').getClientRects().length===0&&document.getElementById('auto-scan').getClientRects().length>0;})()`));
   await client.call('Emulation.setDeviceMetricsOverride',{width:720,height:900,deviceScaleFactor:1,mobile:false});
   assert(await client.evaluate("document.documentElement.scrollWidth<=innerWidth&&document.getElementById('monitor-grid').scrollWidth>document.getElementById('monitor-grid').clientWidth"));
   await client.call('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
   await client.evaluate(`document.querySelector('.monitor-tile[data-udid="mock-4"]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:80,clientY:80}));document.getElementById('device-context-connection').click()`);
   await until(client,"globalMonitor.tiles.get('mock-4').device.enabled===false&&document.querySelectorAll('#selected iframe').length===19");
   assert(await client.evaluate("document.querySelectorAll('.monitor-tile').length===20&&globalMonitor.tiles.get('mock-4').device.ready===false"));
   assert(await client.evaluate("document.getElementById('monitor-notice').textContent==='设备 05 已完成断开'"));
   await client.evaluate(`document.querySelector('.monitor-tile[data-udid="mock-4"]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:80,clientY:80}))`);
   assert.equal(await client.evaluate("document.getElementById('device-context-connection').textContent"),'接入此台');
   await client.evaluate("document.getElementById('device-context-connection').click()");
   await until(client,"globalMonitor.tiles.get('mock-4').device.enabled===true&&document.querySelectorAll('#selected iframe').length===20");
   assert(await client.evaluate("document.getElementById('monitor-notice').textContent==='设备 05 已完成接入，连接已就绪'"));
   await client.evaluate(`window.readonlyFrame=globalMonitor.tiles.get('mock-0').frame;document.querySelector('.monitor-tile[data-udid="mock-0"]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:80,clientY:80}));document.getElementById('device-context-readonly').click()`);
   await until(client,"globalMonitor.tiles.get('mock-0').device.readonly===true");
   assert(await client.evaluate("globalMonitor.tiles.get('mock-0').frame===readonlyFrame&&document.querySelectorAll('#selected iframe').length===20"));
   assert(await client.evaluate("document.getElementById('monitor-notice').textContent==='设备 01 已完成切换为仅监看'"));
   await client.evaluate(`document.querySelector('.monitor-tile[data-udid="mock-0"]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:80,clientY:80}));document.getElementById('device-context-readonly').click()`);
   await until(client,"globalMonitor.tiles.get('mock-0').device.readonly===false");
   await client.evaluate("window.framesBefore=[...document.querySelectorAll('#selected iframe')];document.querySelectorAll('.monitor-tile')[4].click()");
   await until(client,"document.querySelector('.monitor-selected')?.dataset.udid==='mock-4'&&document.querySelector('#device-list .current')?.dataset.udid==='mock-4'");
   await delay(600);
   assert(await client.evaluate("document.querySelector('main').getBoundingClientRect().top<5"));
   assert(await client.evaluate("framesBefore.every((frame,i)=>frame===document.querySelectorAll('#selected iframe')[i])"));
   await client.evaluate("document.getElementById('monitor-back').click()");await until(client,'scrollY<5');
   await client.call('Emulation.setDeviceMetricsOverride',{width:2560,height:1440,deviceScaleFactor:1,mobile:false});
   assert(await client.evaluate("(()=>{const r=document.querySelector('main').getBoundingClientRect();return r.left===0&&Math.abs(r.width-document.documentElement.clientWidth)<1&&getComputedStyle(document.querySelector('main')).paddingLeft==='8px';})()"));
   await client.call('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
   assert(await client.evaluate('scrollY<5'));
   // Real click supplies the user gesture required for browser fullscreen.
   const rect=await client.evaluate("(()=>{const r=document.getElementById('monitor-fullscreen').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()");
   await client.call('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...rect});
   await client.call('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...rect});
   await until(client,'globalMonitor.isFullscreen()');
   await client.evaluate("document.querySelectorAll('.monitor-tile')[2].click()");
   await until(client,"!globalMonitor.isFullscreen()&&document.querySelector('.monitor-selected')?.dataset.udid==='mock-2'");
   // Foreign windows and old request identifiers must not replace an image.
   assert(await client.evaluate(`(()=>{const tile=globalMonitor.tiles.get('mock-2'),old=tile.image.src;globalMonitor.receive({source:window,origin:location.origin,data:{type:'monitor-snapshot-result',id:tile.pending,image:new Blob(['bad'],{type:'image/jpeg'})}});return tile.image.src===old;})()`));
   await client.evaluate("document.getElementById('monitor-back').click()");await until(client,'scrollY<5');
  }
  if(!live){
   await client.evaluate(`window.reconnectFrames=new Map([...cards].map(([id,card])=>[id,card.frame]));document.querySelector('.monitor-tile[data-udid="mock-5"]').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:80,clientY:80}))`);
   assert(await client.evaluate("document.getElementById('device-context-reconnect').title.includes('修复此台信任')"));
   await client.evaluate("document.getElementById('device-context-reconnect').click()");
   await until(client,"document.getElementById('monitor-notice').textContent.includes('检查并修复信任')");
   assert(await client.evaluate("globalMonitor.tiles.get('mock-5').placeholder.textContent.includes('检查并修复信任')&&[...cards].every(([id,card])=>id==='mock-5'||card.frame===reconnectFrames.get(id))"));
   await until(client,"document.getElementById('monitor-notice').textContent.includes('系统会话与连接已重建')");
   await until(client,"document.querySelectorAll('#selected iframe').length===20");
   await until(client,"!globalMonitor.tiles.get('mock-5').image.hidden");
   assert(await client.evaluate("[...cards].every(([id,card])=>id==='mock-5'||card.frame===reconnectFrames.get(id))"));
  }
  const result=await client.evaluate(`({tiles:document.querySelectorAll('.monitor-tile').length,images:document.querySelectorAll('.monitor-screen img:not([hidden])').length,ready:document.getElementById('monitor-count').textContent})`);
  if(!metadataOnly){
   const output=path.join(__dirname,'.device-data/diagnostics');await fs.mkdir(output,{recursive:true});
   const screenshot=await client.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
   await fs.writeFile(path.join(output,live?'global-monitor-live.png':'global-monitor-preview.png'),Buffer.from(screenshot.data,'base64'));
  }
  assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify({live,...result,errors}));
 }finally{
  if(client){try{await client.call('Browser.close');}catch{}client.close();}
  if(server)await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
