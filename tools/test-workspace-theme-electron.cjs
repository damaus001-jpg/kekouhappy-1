// Exercise the real host injection and page styles without an HTTP backend or phones.
const {app,BrowserWindow,session}=require('electron');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const host=process.argv[2];
const folder=path.join(root,'.tmp','workspace-theme-check');
fs.mkdirSync(folder,{recursive:true});
app.setPath('userData',path.join(folder,'profile-'+require('node:crypto').randomUUID()));
app.disableHardwareAcceleration();
const windows=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const report={ok:false,real_backend_contacted:false,phones_contacted:false};
const run=(window,source)=>window.webContents.executeJavaScript(source);
async function snapshot(window){
 return run(window,`(() => {
  const style=selector=>getComputedStyle(document.querySelector(selector));
  return {theme:window.pikachuWorkspaceTheme.current,accent:style('#capture-current').color,
   body:style('body').backgroundColor,background:style('body').backgroundImage,
   warning:style('#test-warning').color,error:style('#test-error').color,
   button:style('#send-reply').backgroundImage,selection:style('#test-selected').borderColor};
 })()`);
}
app.whenReady().then(async()=>{
 const ts=require(path.join(host,'node_modules/typescript'));
 const compiled=ts.transpileModule(fs.readFileSync(path.join(host,'src/workspace-theme-runtime.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
 const module={exports:{}};
 vm.runInNewContext(compiled,{module,exports:module.exports,Promise});
 const bridge=module.exports;
 const isolated=session.fromPartition('theme-check-'+require('node:crypto').randomUUID());
 const allowed={'/':'workspace.html','/dashboard.css':'dashboard.css','/workspace_theme.js':'workspace_theme.js','/brand-logo.jpg':'brand-logo.jpg','/electric-doodles.svg':'electric-doodles.svg'};
 await isolated.protocol.handle('http',request=>{
  const url=new URL(request.url);
  assert.equal(url.origin,'http://127.0.0.1:8070');
  const name=allowed[url.pathname];
  if(!name)return new Response('// Business runtime disabled in this isolated UI test.',{headers:{'Content-Type':'application/javascript'}});
  const types={html:'text/html',css:'text/css',js:'application/javascript',jpg:'image/jpeg',svg:'image/svg+xml'};
  return new Response(fs.readFileSync(path.join(root,'iphone_batch/web',name)),{headers:{'Content-Type':types[name.split('.').pop()]+'; charset=utf-8'}});
 });
 async function open(){
  const window=new BrowserWindow({show:false,width:1550,height:950,webPreferences:{session:isolated,nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false}});
  windows.push(window);await window.loadURL('http://127.0.0.1:8070/');
  await run(window,`document.body.insertAdjacentHTML('beforeend','<span id="test-warning" class="cpu-usage" data-level="high">high</span><div class="work-panel"><span id="test-error" class="message-status failed">failed</span></div><article id="test-selected" class="device-entry current">selected</article>'); document.getElementById('send-reply').disabled=false;`);
  return window;
 }
 const first=await open();
 const original=await snapshot(first);
 assert.equal(original.theme,'blackGold');
 const results={blackGold:original};
 for(const [theme,rgb] of Object.entries({pink:'rgb(255, 112, 182)',murongPurple:'rgb(180, 142, 173)',clearWaterBlue:'rgb(74, 173, 232)'})){
  assert.equal(await run(first,bridge.buildWorkspaceThemeScript(theme)),true);
  const current=await snapshot(first);
  assert.equal(current.accent,rgb);
  assert.equal(current.body,original.body);
  assert.equal(current.warning,original.warning);
  assert.equal(current.error,original.error);
  assert.equal(current.error,'rgb(242, 121, 121)');
  assert.notEqual(current.button,original.button);
  results[theme]=current;
  await run(first,'new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  await pause(100);
  fs.writeFileSync(path.join(folder,theme+'.png'),(await first.webContents.capturePage()).toPNG());
 }
 await run(first,bridge.buildWorkspaceThemeScript('blackGold'));
 assert.deepEqual(await snapshot(first),original,'gold must restore exact computed styles');
 await run(first,bridge.buildWorkspaceThemeScript('pink'));
 const second=await open();
 assert.equal((await snapshot(second)).theme,'pink');
 await run(first,bridge.buildWorkspaceThemeScript('murongPurple'));
 for(let n=0;n<30&&(await snapshot(second)).theme!=='murongPurple';n++)await pause(50);
 assert.equal((await snapshot(second)).theme,'murongPurple','same-origin storage event syncs existing windows');
 const loaded=new Promise(resolve=>first.webContents.once('did-finish-load',resolve));
 first.reload();await loaded;
 assert.equal(await run(first,'window.pikachuWorkspaceTheme.current'),'murongPurple');
 assert.equal(await run(first,bridge.buildWorkspaceThemeScript('pink')),true,'host can resend after reload');
 report.ok=true;report.themes=results;report.gold_restored_exactly=true;report.storage_and_reload=true;report.actual_host_bridge=true;
 console.log('PASS: real Pikachu bridge, four themes, exact gold restoration, dark background, semantic status colors, storage and reload.');
}).catch(error=>{report.error=String(error.stack||error);console.error(error);process.exitCode=1;}).finally(()=>{
 fs.writeFileSync(path.join(folder,'result.json'),JSON.stringify(report,null,2));
 for(const window of windows)if(!window.isDestroyed())window.destroy();
 app.quit();
});
