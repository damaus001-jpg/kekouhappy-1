const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'web/dashboard.js'),'utf8');
const handler=source.slice(source.indexOf("document.getElementById('device-context-reboot').addEventListener"),
    source.indexOf("for(const [id,followup]"));
function setup({confirm=true,device={},status=202}={}){
 const target={udid:'phone-one',name:'iPhone 1',...device},sent=[],notices=[],prompts=[];
 let click;
 const context={deviceMenuTarget:{device:target,index:0},devicePreview:false,workspaceBusy:false,busy:false,
  reconnectRequests:new Set(),reconnectNotices:new Map(),AbortSignal,
  document:{getElementById:()=>({addEventListener:(_,fn)=>{click=fn;}})},
  deviceLabel:()=>({number:'01'}),closeDeviceMenu(){context.deviceMenuTarget=null;},
  window:{confirm(text){prompts.push(text);return confirm;}},notice:text=>notices.push(text),refresh(){},
  fetch:async(url,options)=>{sent.push({url,body:JSON.parse(options.body)});return {ok:status===202,json:async()=>({job:'job-one',error:'denied'})};}};
 vm.runInNewContext(handler,context);
 return {click,sent,notices,prompts,context};
}
(async()=>{
 let s=setup({confirm:false});await s.click();assert.equal(s.sent.length,0);assert.equal(s.prompts.length,1);
 s=setup();await s.click();assert.deepEqual(s.sent,[{url:'/api/devices/reboot',body:{device:'phone-one',confirm:'phone-one'}}]);
 assert(s.prompts[0].includes('01'));assert(s.prompts[0].includes('密码解锁'));
 assert.equal(s.context.reconnectNotices.get('phone-one').operation,'reboot');
 for(const device of [{readonly:true},{enabled:false},{trust_pending:true},{reconnecting:true}]){
  s=setup({device});await s.click();assert.equal(s.sent.length,0);assert.equal(s.prompts.length,0);
 }
 s=setup();s.context.reconnectRequests.add('phone-one');await s.click();assert.equal(s.sent.length,0);
 s=setup({status:503});await s.click();assert.equal(s.sent.length,1);assert.equal(s.context.reconnectNotices.size,0);
 assert(s.notices.at(-1).includes('未自动重复发送'));
 console.log('Reboot menu passed: target confirmation, cancel, policy guards, one request and uncertain-response feedback');
})().catch(error=>{console.error(error);process.exitCode=1;});
