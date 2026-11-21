const {app,BrowserWindow,session,ipcMain,dialog,Menu,shell}=require('electron');
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),http=require('node:http');
const {spawn}=require('node:child_process'),{pathToFileURL}=require('node:url');
const {headers,target}=require('./access.cjs');
const ROOT=path.resolve(__dirname,'../../..'),PYTHON=path.join(ROOT,'runtime','python.exe');
const checkAt=process.argv.indexOf('--check-desktop'),check=checkAt>=0,report=check?process.argv[checkAt+1]:null;
if(check){if(!report)throw Error('Missing desktop report path');process.env.LOCALAPPDATA=path.join(path.dirname(report),'desktop-check-local');}
app.setName('PhoneWorkbench8070');app.setAppUserModelId('PhoneWorkbench8070.Desktop');
app.setPath('userData',path.join(process.env.LOCALAPPDATA,'PhoneWorkbench8070','desktop'));
let window,child;
const env=()=>({...process.env,PATH:path.join(ROOT,'runtime')+path.delimiter+process.env.PATH,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'});
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function runPython(args){return new Promise((resolve,reject)=>{
 const child=spawn(PYTHON,args,{cwd:path.join(ROOT,'iphone_batch'),env:env(),windowsHide:true,stdio:['ignore','pipe','pipe']});let out='',err='';
 child.stdout.on('data',data=>out+=data);child.stderr.on('data',data=>err+=data);child.on('error',reject);
 child.on('exit',code=>code===0?resolve(out.trim()):reject(Error((err||out||'后台启动失败').slice(-1500))));
});}
function signedStatus(url){return new Promise((resolve,reject)=>{const request=http.get(url,{headers:headers('GET',url)},response=>{response.resume();resolve(response.statusCode);});request.setTimeout(2000,()=>request.destroy(Error('后台尚未就绪')));request.on('error',reject);});}
function manager(){spawn(path.join(ROOT,'runtime','pythonw.exe'),[path.join(ROOT,'BackendControl.pyw')],{cwd:ROOT,env:env(),windowsHide:true,stdio:'ignore'}).on('error',error=>dialog.showErrorBox('后台管理',error.message));return {message:'后台管理窗口已打开。'};}
async function open(){const url='http://127.0.0.1:8070/';if(await signedStatus(url)!==200)throw Error('工作台未启动或访问校验失败，请先启动后台。');await window.loadURL(url);return {message:'工作台已打开。'};}
async function start(){await runPython(['-c','from backend_control import Backend; print(Backend().start())']);return open();}
function requireWelcome(event){if(event.senderFrame.url!==pathToFileURL(path.join(__dirname,'welcome.html')).href)throw Error('此操作只允许从桌面启动页发起');}
async function main(){
 const trusted=session.fromPartition(check?'installer-check':'persist:workbench-8070');
 trusted.webRequest.onBeforeSendHeaders((details,callback)=>{try{callback({requestHeaders:headers(details.method,details.url,details.requestHeaders)});}catch{callback({cancel:true});}});
 trusted.setPermissionRequestHandler((contents,permission,callback)=>callback(['notifications','clipboard-sanitized-write'].includes(permission)&&target(contents.getURL())));
 window=new BrowserWindow({width:1450,height:960,minWidth:950,minHeight:650,show:!check,backgroundColor:'#101713',webPreferences:{session:trusted,preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
 window.webContents.setWindowOpenHandler(({url})=>{if(/^https?:\/\//i.test(url)&&!target(url))shell.openExternal(url);return {action:'deny'};});
 window.webContents.on('will-navigate',(event,url)=>{if(!target(url)&&url!==pathToFileURL(path.join(__dirname,'welcome.html')).href)event.preventDefault();});
 if(check){
  const listener=net.createServer();await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));
  const folder=path.join(path.dirname(report),'isolated-dashboard');fs.mkdirSync(folder,{recursive:true});
  child=spawn(PYTHON,['-c','import controller; controller.discover=lambda:[]; import dashboard; dashboard.main()','--port',String(port),'--device-map',path.join(folder,'devices.json')],{cwd:path.join(ROOT,'iphone_batch'),env:env(),windowsHide:true,stdio:'ignore'});
  const base=`http://127.0.0.1:${port}`;let ready=false;
  for(let attempt=0;attempt<120;attempt++){try{if(await signedStatus(base+'/')===200){ready=true;break;}}catch{}await delay(150);}
  if(!ready)throw Error('Isolated zero-device dashboard did not start');
  const unsigned=session.fromPartition('installer-untrusted');const denied=(await unsigned.fetch(base+'/')).status;
  if(denied!==403)throw Error('Unsigned page was not denied');
  await window.loadURL(base+'/');
  const result=await window.webContents.executeJavaScript(`fetch('/api/state').then(async r=>({status:r.status,data:await r.json(),ui:!!document.getElementById('new-sms-task'),version:document.querySelector('.app-version').textContent}))`);
  if(result.status!==200||result.data.devices.length!==0||!result.ui)throw Error('Signed desktop UI check failed');
  fs.writeFileSync(report,JSON.stringify({ok:true,unsigned_status:denied,signed_status:result.status,version:result.version,new_sms_entry:result.ui,devices:0,phone_connections_tested:false},null,2));
  return;
 }
 ipcMain.handle('workbench:start',event=>{requireWelcome(event);return start();});
 ipcMain.handle('workbench:open',event=>{requireWelcome(event);return open();});
 ipcMain.handle('workbench:control',event=>{requireWelcome(event);return manager();});
 Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'工作台',submenu:[{label:'启动并打开',click:()=>start().catch(e=>dialog.showErrorBox('工作台',e.message))},{label:'打开已运行后台',click:()=>open().catch(e=>dialog.showErrorBox('工作台',e.message))},{label:'后台管理',click:manager},{type:'separator'},{role:'quit',label:'退出客户端'}]},{label:'视图',submenu:[{role:'reload',label:'刷新'},{role:'resetZoom',label:'实际大小'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},{role:'togglefullscreen',label:'全屏'}]}]));
 await window.loadFile(path.join(__dirname,'welcome.html'));
}
if(!check&&!app.requestSingleInstanceLock())app.quit();else{
 app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});
 app.whenReady().then(main).catch(error=>{if(check){fs.writeFileSync(report,JSON.stringify({ok:false,error:error.stack}));process.exitCode=1;}else dialog.showErrorBox('手机工作台 8070',error.message);}).finally(()=>{if(check){if(child)child.kill();if(window&&!window.isDestroyed())window.destroy();app.quit();}});
 app.on('window-all-closed',()=>app.quit());
}
