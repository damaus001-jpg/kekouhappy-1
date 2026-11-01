const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'web/dashboard.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'web/workspace.html'), 'utf8');
const stored = new Map();

function build(preview=true) {
 const nodes = new Map(), requests=[];
 function element() {
  return {children: [], listeners: {}, style: {}, attrs: {}, dataset:{}, value: '', textContent: '',
   remove(){},querySelector(){return null;},classList: {toggle() {}}, setAttribute(k,v) {this.attrs[k]=v;},
   append(...xs) {for(const x of xs)x.parentElement=this;this.children.push(...xs);}, replaceChildren() {this.children=[];},
   addEventListener(k,f) {this.listeners[k]=f;}, showModal() {this.open=true;},
   close() {this.open=false;}, focus() {}, contains(t) {return t===this;},
   getBoundingClientRect() {return {width:160,height:130,left:20,bottom:80};}};
 }
 for (const match of html.matchAll(/id="([^"]+)"/g)) nodes.set(match[1],element());
 const context = {document: {
  getElementById(id) {assert(nodes.has(id),'Missing HTML element '+id);return nodes.get(id);},
  querySelector() {return element();}, querySelectorAll(){return [];}, createElement: element, body: element(), addEventListener() {}
 }, window: {innerWidth:1000,innerHeight:800,addEventListener() {}},
 location: {hash:preview?'#preview-devices':'',origin:'http://127.0.0.1:8070'},setTimeout(){},setInterval(){},navigator:{},
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
 return {nodes,context,entries,find,menu,requests};
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

(async()=>{
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
