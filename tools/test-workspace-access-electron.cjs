// A hidden Electron window and an isolated dashboard, with USB discovery disabled.
const {app,BrowserWindow,session}=require('electron');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const http=require('node:http');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const translator=process.argv[2];
const folder=path.join(root,'iphone_batch','.device-data','diagnostics','auth-browser-'+require('node:crypto').randomUUID());
fs.mkdirSync(folder,{recursive:true});
fs.mkdirSync(path.join(folder,'electron'),{recursive:true});
const resultFile=path.join(root,'iphone_batch','.device-data','diagnostics','access-browser-result.json');
fs.writeFileSync(resultFile,JSON.stringify({status:'started',folder}));
process.on('uncaughtException',error=>{fs.writeFileSync(resultFile,JSON.stringify({status:'failed',error:String(error)}));process.exit(1);});
process.env.LOCALAPPDATA=folder;
app.setPath('userData',path.join(folder,'electron'));
app.disableHardwareAcceleration();
let child,window;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function status(url){
  return new Promise((resolve,reject)=>{
    const request=http.get(url,response=>{response.resume();resolve(response.statusCode);});
    request.setTimeout(500,()=>request.destroy());request.on('error',reject);
  });
}
app.whenReady().then(async()=>{
  const bridge=await import(pathToFileURL(path.join(translator,'dist-electron','workspace-access.js')).href);
  const listener=net.createServer();
  await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));
  const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));
  const base=`http://127.0.0.1:${port}`;
  child=spawn(path.join(root,'.venv','Scripts','python.exe'),['-c','import controller; controller.discover=lambda:[]; import dashboard; dashboard.main()','--port',String(port),'--device-map',path.join(folder,'devices.json')],
    {cwd:path.join(root,'iphone_batch'),env:process.env,windowsHide:true,stdio:'ignore'});
  let ready=false;
  for(let attempt=0;attempt<150;attempt++){
    try{if(await status(base+'/')===403){ready=true;break;}}catch{}
    await pause(100);
  }
  assert.ok(ready,'isolated gateway must start');
  const untrusted=session.fromPartition('untrusted-test');
  assert.equal((await untrusted.fetch(base+'/')).status,403);
  const trusted=session.fromPartition('apple-test');
  trusted.webRequest.onBeforeSendHeaders((details,callback)=>{
    try{callback({requestHeaders:bridge.workspaceAccessHeaders('apple',details.method,details.url,details.requestHeaders)});}
    catch{callback({cancel:true});}
  });
  window=new BrowserWindow({show:false,webPreferences:{session:trusted,nodeIntegration:false,contextIsolation:true,sandbox:true}});
  await window.loadURL(base+'/');
  assert.ok(await window.webContents.executeJavaScript('Boolean(document.querySelector("#capture-current"))'));
  const data=await window.webContents.executeJavaScript('fetch("/api/state").then(async r=>({status:r.status,data:await r.json()}))');
  assert.equal(data.status,200);assert.deepEqual(data.data.devices,[]);
  const menu=await window.webContents.executeJavaScript(`(() => {
    showDeviceMenu({preventDefault(){},clientX:10,clientY:10},previewDevices[0],0);
    const opened=!document.getElementById('device-context-menu').hidden;
    const reconnect=Boolean(document.getElementById('device-context-reconnect'));
    document.body.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
    const outsideClosed=document.getElementById('device-context-menu').hidden;
    showDeviceMenu({preventDefault(){},clientX:10,clientY:10},previewDevices[0],0);
    window.dispatchEvent(new Event('blur'));
    return {opened,reconnect,outsideClosed,iframeFocusClosed:document.getElementById('device-context-menu').hidden};
  })()`);
  assert.deepEqual(menu,{opened:true,reconnect:true,outsideClosed:true,iframeFocusClosed:true});
  console.log('PASS: unsigned browser denied; signed Electron page rendered; page API request authenticated; no phones connected.');
  fs.writeFileSync(resultFile,JSON.stringify({status:'passed',checks:['unsigned-403','signed-page-rendered','signed-renderer-api-200','single-reconnect-menu','outside-click-closes','iframe-blur-closes','zero-devices']}));
}).catch(error=>{fs.writeFileSync(resultFile,JSON.stringify({status:'failed',error:String(error)}));console.error(error);process.exitCode=1;}).finally(()=>{
  if(window&&!window.isDestroyed())window.destroy();
  if(child)child.kill();
  app.quit();
});
