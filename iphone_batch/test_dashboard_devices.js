const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'web/dashboard.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'web/workspace.html'), 'utf8');
const stored = new Map();

function build(preview=true) {
 const nodes = new Map(), requests=[], windowListeners={};
 function element(tag) {
  return {children: [], listeners: {}, style: {}, attrs: {}, dataset:{}, value: '', textContent: '',
   contentWindow:tag==='iframe'?{messages:[],postMessage(message,origin){this.messages.push({message,origin});}}:undefined,
   remove(){if(this.parentElement){const parent=this.parentElement;parent.children=parent.children.filter(x=>x!==this);this.parentElement=null;}},querySelector(){return null;},classList: {toggle() {}}, setAttribute(k,v) {this.attrs[k]=v;},
   append(...xs) {for(const x of xs){x.remove();x.parentElement=this;this.children.push(x);}}, replaceChildren() {for(const x of this.children)x.parentElement=null;this.children=[];},
   addEventListener(k,f) {this.listeners[k]=f;}, showModal() {this.open=true;},
   close() {this.open=false;}, focus() {}, contains(t) {return t===this;},
   getBoundingClientRect() {return {width:160,height:130,left:20,bottom:80};}};
 }
 for (const match of html.matchAll(/id="([^"]+)"/g)) nodes.set(match[1],Object.assign(element(),{id:match[1]}));
 const context = {document: {
  getElementById(id) {assert(nodes.has(id),'Missing HTML element '+id);return nodes.get(id);},
  querySelector() {return element();}, querySelectorAll(){return [];}, createElement: element, body: element(), addEventListener() {}
 }, window: {innerWidth:1000,innerHeight:800,addEventListener(name,listener) {(windowListeners[name]??=[]).push(listener);}},
 location: {hash:preview?'#preview-devices':'',origin:'http://127.0.0.1:8070'},setTimeout(){},clearTimeout(){},setInterval(){},AbortController,navigator:{},
 fetch(url,options){
  requests.push({url,body:options?.body?JSON.parse(options.body):null});
  if(url==='/api/select')return Promise.resolve({ok:true,json:async()=>({selected:'setup-phone',active:null})});
  if(url==='/api/developer-mode/reveal')return Promise.resolve({ok:true,json:async()=>({message:'已请求显示入口'})});
  return new Promise(()=>{});
 },
 localStorage: {getItem(k) {return stored.get(k)||null;},setItem(k,v) {stored.set(k,v);}},
 console};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8'),context);
 vm.runInContext(source,context);
 const entries=()=>nodes.get('device-list').children.map(tile=>tile.children[0]);
 const find=number=>nodes.get('device-list').children.find(tile=>tile.children[0].children[1].textContent.endsWith(' '+number));
 const menu=number=>find(number).listeners.contextmenu({preventDefault() {},clientX:20,clientY:20});
 return {nodes,context,entries,find,menu,requests,emit(event){for(const fn of windowListeners.message||[])fn(event);}};
}

let app=build();
assert.equal(app.entries().length,20);
assert(app.entries()[0].children[1].textContent.endsWith(' 01'));
assert.equal(app.nodes.get('device-followup').disabled,true);
app.find('01').children[0].onclick();
assert.equal(app.nodes.get('device-followup').checked,false);
app.nodes.get('device-followup').checked=true;
app.nodes.get('device-followup').listeners.change();
assert(app.entries()[0].children[1].textContent.endsWith(' 01'));
assert(app.find('01').children[0].children[2].textContent.endsWith(' 1'));
const selectContact=index=>{
 vm.runInContext('currentConversationId=savedConversations['+index+'].id;renderConversation();',app.context);
};
selectContact(1);
assert.equal(app.nodes.get('device-followup').checked,false);
app.nodes.get('device-followup').checked=true;app.nodes.get('device-followup').listeners.change();
assert(app.find('01').children[0].children[2].textContent.endsWith(' 2'));
selectContact(0);
assert.equal(app.nodes.get('device-followup').checked,true);
vm.runInContext("savedConversations[0]={...savedConversations[0],id:'new-snapshot',phone_number:'+1 (555) 000-0001'};currentConversationId='new-snapshot';renderConversation();",app.context);
assert.equal(app.nodes.get('device-followup').checked,true);
app.nodes.get('device-followup').listeners.change();
assert(app.find('01').children[0].children[2].textContent.endsWith(' 2'));
app.find('02').children[0].onclick();
assert.equal(app.nodes.get('device-followup').checked,false);
app.nodes.get('device-followup').checked=true;app.nodes.get('device-followup').listeners.change();
assert(app.find('02').children[0].children[2].textContent.endsWith(' 1'));
app.menu('03');app.nodes.get('device-context-followup').listeners.click();
assert(app.find('03').children[0].children[2].textContent.endsWith(' 0'));
assert(app.entries()[0].children[1].textContent.endsWith(' 01'));
app.nodes.get('device-sort').value='unread';app.nodes.get('device-sort').listeners.change();
assert(app.entries()[0].children[1].textContent.endsWith(' 20'));
assert.equal(app.nodes.get('device-followup').checked,true);
const counts=app.entries().map(entry=>Number(entry.children[0].children[0]?.textContent||0));
assert.deepEqual(counts,[...counts].sort((a,b)=>b-a));
app.menu('01');app.nodes.get('device-context-edit').listeners.click();
app.nodes.get('device-number-input').value='A01';
app.nodes.get('device-label-form').listeners.submit({preventDefault() {}});
assert(app.find('A01').children[0].children[2].className.includes('followup'));
assert(app.find('A01').children[0].children[2].textContent.endsWith(' 2'));
app=build();
assert.equal(app.nodes.get('device-sort').value,'unread');
assert(app.find('A01').children[0].children[2].className.includes('followup'));
app.find('A01').children[0].onclick();
assert.equal(app.nodes.get('device-followup').checked,true);
app.nodes.get('device-followup').checked=false;
app.nodes.get('device-followup').listeners.change();
assert(app.find('A01').children[0].children[2].textContent.endsWith(' 1'));
selectContact(1);
assert.equal(app.nodes.get('device-followup').checked,true);
selectContact(0);
assert.equal(app.nodes.get('device-followup').checked,false);
app.nodes.get('followup-contact-list').children[0].onclick();
assert.equal(app.nodes.get('device-followup').checked,true);
assert.equal(app.nodes.get('followup-contact-count').textContent,'1');
app.context.localStorage.setItem=()=>{throw Error('Storage unavailable');};
app.nodes.get('device-followup').checked=false;
app.nodes.get('device-followup').listeners.change();
assert.equal(app.nodes.get('device-followup').checked,true);
assert(app.find('A01').children[0].children[2].className.includes('followup'));
vm.runInContext('previewDevices[5].ready=true;previewDevices[9].ready=true;render(previewDevices,previewSelection);',app.context);
assert(app.entries()[0].children[1].textContent.endsWith(' 06'));
assert(app.entries()[1].children[1].textContent.endsWith(' 10'));
assert.equal(app.entries()[0].dataset.udid,'preview-device-6');
app.nodes.get('device-sort').value='followup';app.nodes.get('device-sort').listeners.change();
assert(app.entries()[0].children[1].textContent.endsWith(' 06'));
assert(app.entries()[1].children[1].textContent.endsWith(' 10'));
assert(app.entries()[2].children[1].textContent.endsWith(' A01'));
console.log('Device UI passed: available viewers first in both sorts, stable labels, per-contact counts, persistence and save failure');

{
 const live=build(false);
 vm.runInContext(`
 loadWorkspace=()=>{};
 const phones=Array.from({length:20},(_,i)=>({udid:'phone-'+i,name:'iPhone '+i,port:8080+i,ready:true}));
 render(phones,null,null);
 `,live.context);
 const frames=()=>vm.runInContext('[...cards.values()].filter(c=>c.frame).map(c=>c.frame)',live.context);
 assert.equal(frames().length,0,'unselected devices never mount a viewer');
 vm.runInContext("render(phones,'phone-19','phone-19')",live.context);
 assert.equal(frames().length,1,'only the selected device mounts a viewer out of 20');
 const first=frames()[0];first.onload();
 assert.equal(first.contentWindow.messages.at(-1).message.visible,true);
 vm.runInContext("render(phones,'phone-19','phone-19')",live.context);
 assert.equal(frames()[0],first,'polling retains the current viewer');
 vm.runInContext("render(phones,'phone-0','phone-0')",live.context);
 assert.equal(frames().length,1);
 assert.equal(first.parentElement,null,'switching releases the old iframe and its decoder');
 assert.equal(first.onload,null,'a removed viewer cannot send a stale load notification');
 const second=frames()[0];
 assert.notEqual(second,first);
 vm.runInContext("render(phones,'phone-0',null)",live.context);
 assert.equal(frames()[0],second,'temporary control pause does not restart selected video');
 vm.runInContext("render(phones,'phone-19','phone-19')",live.context);
 assert.notEqual(frames()[0],first,'returning opens a fresh stream instead of replaying old frames');
 vm.runInContext("phones[19].ready=false;render(phones,'phone-19',null)",live.context);
 assert.equal(frames().length,0,'unready selection releases video');
 vm.runInContext('render([],null,null)',live.context);
 assert.equal(frames().length,0);
 console.log('Selected video lifecycle passed: 20 standby devices, one viewer, polling reuse, switch/reselect, control pause and disconnect');
}

(async()=>{
 const recovery=build(false);
 vm.runInContext("loadWorkspace=()=>{};render([{udid:'one',name:'iPhone',port:8080,ready:true}],'one','one');refresh=async()=>{};",recovery.context);
 const card=vm.runInContext("cards.get('one')",recovery.context);
 const healthEvent={origin:card.origin,source:card.frame.contentWindow,data:{type:'input-health-result',state:'ready',ready:true}};
 recovery.emit({...healthEvent,source:{}});
 assert.notEqual(card.connectionNotice.hidden,true,'foreign window cannot claim input is ready');
 recovery.emit(healthEvent);assert.equal(card.connectionNotice.hidden,true);
 assert.equal(card.inputReady,true);
 recovery.emit({...healthEvent,data:{type:'input-health-result',state:'unavailable',ready:false}});
 assert.equal(card.connectionNotice.hidden,false);
 assert.equal(card.inputReady,false);
 assert.match(card.connectionNotice.textContent,/刷新/);
 recovery.context.fetch=async url=>({ok:true,json:async()=>url==='/api/devices/refresh'?{count:1}:{}});
 await recovery.nodes.get('refresh-devices').listeners.click();
 assert.equal(card.frame.contentWindow.messages.at(-1).message.type,'input-recover','manual refresh requests input repair on the selected viewer');
 vm.runInContext('workspaceBusy=true;syncWorkspaceControls()',recovery.context);
 assert.equal(card.frame.contentWindow.messages.at(-1).message.working,true,'workspace tasks pause input health checks immediately');
 assert.equal(recovery.nodes.get('refresh-devices').disabled,false,'refresh stays clickable while a phone task runs');
 let refreshCalls=0,finishRefresh;
 recovery.context.fetch=async()=>{refreshCalls++;return new Promise(resolve=>{finishRefresh=()=>resolve({ok:true,json:async()=>({count:1})});});};
 await recovery.nodes.get('refresh-devices').listeners.click();
 await recovery.nodes.get('refresh-devices').listeners.click();
 assert.equal(refreshCalls,0,'refresh waits for the active task instead of interrupting it');
 assert.match(recovery.nodes.get('archive-status').textContent,/已安排设备刷新/);
 vm.runInContext('workspaceBusy=false;syncWorkspaceControls()',recovery.context);
 assert.equal(refreshCalls,1,'task completion starts exactly one queued refresh');
 assert.equal(recovery.nodes.get('refresh-devices').disabled,true);
 finishRefresh();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(recovery.nodes.get('refresh-devices').disabled,false);
 vm.runInContext('busy=true;syncDeviceRefreshControls()',recovery.context);
 assert.equal(recovery.nodes.get('refresh-devices').disabled,false,'selection cannot hide the recovery action');
 await recovery.nodes.get('refresh-devices').listeners.click();
 assert.equal(refreshCalls,1);
 vm.runInContext('busy=false;syncDeviceRefreshControls()',recovery.context);
 assert.equal(refreshCalls,2);
 finishRefresh();await new Promise(resolve=>setImmediate(resolve));
 recovery.context.setTimeout=callback=>setImmediate(callback);
 recovery.context.clearTimeout=timer=>clearImmediate(timer);
 recovery.context.fetch=(_url,{signal})=>new Promise((resolve,reject)=>{
  signal.addEventListener('abort',()=>{const error=new Error('aborted');error.name='AbortError';reject(error);});
 });
 await assert.rejects(vm.runInContext("deviceRequest('/never',{})",recovery.context),/超时/);
 console.log('Input recovery UI passed: trusted status, visible failure, refresh fallback and task pause');

 const live=build(false);
 vm.runInContext(`loadWorkspace=()=>{};render([{udid:'setup-phone',name:'iPhone',port:8080,ready:false,error:'开发者模式未开启'}],null,null);`,live.context);
 assert.equal(live.entries()[0].disabled,false,'USB phone is selectable before its viewer is ready');
 await live.entries()[0].onclick();
 assert.equal(live.entries()[0].attrs['aria-pressed'],'true');
 assert.equal(live.nodes.get('reveal-developer-mode').disabled,false);
 assert.equal(live.nodes.get('phone-home').disabled,true,'setup selection cannot control the phone');
 await live.nodes.get('reveal-developer-mode').listeners.click();
 assert.equal(live.requests.find(r=>r.url==='/api/developer-mode/reveal').body.device,'setup-phone');
 assert.match(live.nodes.get('developer-mode-status').textContent,/已请求显示入口/);
 vm.runInContext(`render(latest,'setup-phone',null);`,live.context);
 assert.equal(live.entries()[0].attrs['aria-pressed'],'true','selection survives state polling without a control owner');
 vm.runInContext(`render([],null,null);`,live.context);
 assert.equal(live.nodes.get('reveal-developer-mode').disabled,true,'disconnect clears setup action');
 console.log('Device setup selection passed: unready USB device selectable, targeted developer request, control stays disabled, polling retains selection, disconnect disables action');
})().catch(error=>{console.error(error);process.exitCode=1;});
