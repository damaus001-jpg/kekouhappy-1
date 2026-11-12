/* Browser verification against simulated phones; --live only observes thumbnails. */
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const web=path.join(__dirname,'web');
async function until(client,expression,timeout=15000){
 const end=Date.now()+timeout;while(Date.now()<end){if(await client.evaluate(expression))return;await delay(150);}throw Error('Timed out: '+expression);
}
async function main(){
 const live=process.argv.includes('--live');let selected=null,server=null,port=8070;
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
   if(url.pathname==='/api/state')return json({active:selected,selected,scan_enabled:false,devices:Array.from({length:20},(_,i)=>({udid:'mock-'+i,name:'iPhone '+(i+1),number:String(i+1).padStart(2,'0'),port,ready:true,control_ready:true}))});
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
  const errors=[];
  client.socket.addEventListener('message',event=>{const data=JSON.parse(String(event.data));if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.exception?.description||data.params.exceptionDetails.text);});
  await client.call('Runtime.enable');await client.call('Page.enable');
  await client.call('Emulation.setDeviceMetricsOverride',{width:1920,height:1080,deviceScaleFactor:1,mobile:false});
  if(live){
   const key=Buffer.from((await fs.readFile(path.join(process.env.LOCALAPPDATA,'PikachuSmsBridge/workspace-access.key'),'ascii')).trim(),'hex');
   client.socket.addEventListener('message',event=>{
    const data=JSON.parse(String(event.data));if(data.method!=='Fetch.requestPaused')return;
    const {requestId,request}=data.params,url=new URL(request.url);
    // Observe live video only: never select a phone, send keys or submit SMS.
    if(request.method!=='GET'&&url.pathname!=='/input-health'){
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
  if(!live){
   await until(client,"document.querySelectorAll('.monitor-screen img:not([hidden])').length===20");
   const geometry=await client.evaluate(`(()=>{const tiles=[...document.querySelectorAll('.monitor-tile')].map(e=>e.getBoundingClientRect()),main=document.querySelector('main').getBoundingClientRect(),wall=document.getElementById('global-monitor').getBoundingClientRect();return {count:tiles.length,columns:tiles.filter(r=>Math.abs(r.top-tiles[0].top)<1).length,below:main.top>=wall.bottom-1,overflow:document.documentElement.scrollWidth>innerWidth};})()`);
   assert.deepEqual(geometry,{count:20,columns:10,below:true,overflow:false});
   await client.evaluate("window.framesBefore=[...document.querySelectorAll('#selected iframe')];document.querySelectorAll('.monitor-tile')[4].click()");
   await until(client,"document.querySelector('.monitor-selected')?.dataset.udid==='mock-4'&&document.querySelector('#device-list .current')?.dataset.udid==='mock-4'");
   await delay(600);
   assert(await client.evaluate("document.querySelector('main').getBoundingClientRect().top<5"));
   assert(await client.evaluate("framesBefore.every((frame,i)=>frame===document.querySelectorAll('#selected iframe')[i])"));
   await client.evaluate("document.getElementById('monitor-back').click()");await delay(600);
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
   await client.evaluate("document.getElementById('monitor-back').click()");await delay(600);
  }
  const result=await client.evaluate(`({tiles:document.querySelectorAll('.monitor-tile').length,images:document.querySelectorAll('.monitor-screen img:not([hidden])').length,ready:document.getElementById('monitor-count').textContent})`);
  const output=path.join(__dirname,'.device-data/diagnostics');await fs.mkdir(output,{recursive:true});
  const screenshot=await client.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await fs.writeFile(path.join(output,live?'global-monitor-live.png':'global-monitor-preview.png'),Buffer.from(screenshot.data,'base64'));
  assert.equal(errors.length,0,errors.join('\n'));console.log(JSON.stringify({live,...result,errors}));
 }finally{
  if(client){try{await client.call('Browser.close');}catch{}client.close();}
  if(server)await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});
 }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
