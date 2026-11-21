const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'web/viewer.js'),'utf8');
const code=source.slice(source.indexOf('async function postJson('),source.indexOf('let activePointer = null;'));
(async()=>{
 const sent=[],errors=[];
 const context=vm.createContext({batchActive:true,controlAvailable:()=>false,AbortSignal,
  inputMonitor:null,reportManualInputFailure:(path,error)=>errors.push(error),
  fetch:async(path,options)=>{sent.push({path,payload:JSON.parse(options.body)});return {ok:true};}});
 vm.runInContext(code,context);
 assert.equal(await context.postJson('/key',{usages:[]}),true);
 assert.equal(await context.postJson('/key',{usages:[4]}),false);
 assert.equal(sent.length,1,'only key release bypasses lost readiness');
 context.batchActive=false;
 assert.equal(await context.postJson('/key',{usages:[]}),false,'inactive devices cannot receive even cleanup');
 assert.equal(sent.length,1);
 console.log('Control cleanup passed: release while unready, reject presses and inactive devices.');
})().catch(error=>{console.error(error);process.exitCode=1;});
