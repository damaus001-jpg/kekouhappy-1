const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../iphone_batch/web/workspace_theme.js'),'utf8');
const key='pikachu-workspace-theme-v1';
function page(saved,blocked=false){
 const values=new Map(),listeners=new Map(),storage=new Map(saved?[[key,saved]]:[]);
 const root={dataset:{},style:{setProperty:(name,value)=>values.set(name,value),removeProperty:name=>values.delete(name)}};
 const context={document:{documentElement:root},localStorage:{
  getItem:name=>{if(blocked)throw Error('Storage unavailable');return storage.get(name)??null;},
  setItem:(name,value)=>{if(blocked)throw Error('Storage unavailable');storage.set(name,value);}
 }};
 context.window={addEventListener:(name,handler)=>listeners.set(name,handler)};
 vm.runInNewContext(source,context);
 return {api:context.window.pikachuWorkspaceTheme,root,values,storage,event:event=>listeners.get('storage')(event)};
}
const p=page();
assert.equal(p.api.current,'blackGold');
assert.equal(p.values.size,0);
for(const request of [null,[],{},'pink',{version:2,theme:'pink'},{version:1,theme:'__proto__'},{version:1,theme:'pink; color:red'}]){
 assert.equal(p.api.apply(request),false);
 assert.equal(p.api.current,'blackGold');
 assert.equal(p.storage.size,0);
}
for(const [theme,color] of Object.entries({pink:'#FF70B6',murongPurple:'#B48EAD',clearWaterBlue:'#4AADE8'})){
 assert.equal(p.api.apply({version:1,theme}),true);
 assert.equal(p.values.get('--workspace-accent'),color);
 assert.equal(p.storage.get(key),theme);
 assert.equal(page(p.storage.get(key)).api.current,theme,'reload restores last accepted host theme');
}
p.api.apply({version:1,theme:'blackGold'});
assert.equal(p.values.size,0,'gold removes every override so original CSS is restored');
p.event({key,newValue:'pink'});
assert.equal(p.api.current,'pink');
p.event({key,newValue:'invalid'});
assert.equal(p.api.current,'pink');
p.event({key,newValue:null});
assert.equal(p.api.current,'blackGold');
assert.equal(page('corrupt').api.current,'blackGold');
assert.equal(page(null,true).api.apply({version:1,theme:'pink'}),true,'denied storage cannot break live theming');
p.api.apply({version:1,theme:'pink'});
const css=fs.readFileSync(path.join(__dirname,'../iphone_batch/web/dashboard.css'),'utf8');
for(const [,name] of css.matchAll(/var\((--workspace-accent[\w-]*),/g))assert.ok(p.values.has(name),name);
console.log('Workspace theme protocol, invalid input, persistence, storage events, denied storage, exact gold reset and CSS palette coverage passed.');
