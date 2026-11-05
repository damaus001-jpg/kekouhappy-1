const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'web/viewer.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('class VideoConnection {'),source.indexOf('// The dashboard keeps ready previews'))+'\nglobalThis.Connection=VideoConnection;',context);
(async()=>{
 let now=0,selected=false,id=0;const tasks=new Map(),delays=[];
 const connection=new context.Connection({selected:()=>selected,now:()=>now,
  setTimer:(fn,ms)=>{delays.push(ms);tasks.set(++id,fn);return id;},clearTimer:n=>tasks.delete(n)});
 connection.connected();connection.frame();now=10000;
 assert.equal(connection.state,'streaming','static screens do not become disconnected');
 connection.disconnected();let complete=false;
 const first=connection.waitRetry().then(()=>complete=true);assert.equal(delays.at(-1),0,'first lost connection retries immediately');
 tasks.get(id)();await first;assert.ok(complete);
 connection.waitRetry();assert.equal(delays.at(-1),500);
 selected=true;connection.promote();await Promise.resolve();assert.equal(connection.timer,null,'selecting wakes pending background retry');
 for(let i=0;i<8;i++){connection.waitRetry();assert.ok(delays.at(-1)<=1000);connection.promote();}
 connection.frame();connection.disconnected();connection.waitRetry();assert.equal(delays.at(-1),0,'a healthy recovered frame resets backoff');connection.promote();
 const offline=context;
 const ticks=[];
 Object.assign(offline,{document:{getElementById:()=>({classList:{hidden:true,add(){this.hidden=true;},toggle(_name,on){this.hidden=on;}}})},setInterval:fn=>ticks.push(fn)});
 vm.runInContext(`let batchManaged=true,batchSelected=true,frameCount=1;
 const videoConnection={state:'streaming',outageMs:()=>10000};
 ${source.slice(source.indexOf('const offlineOverlay ='),source.indexOf('// ----- Collapse recovery is SERVER-side'))}
 globalThis.hidden=()=>offlineOverlay.classList.hidden;globalThis.markDisconnected=()=>videoConnection.state='retrying';`,offline);
 ticks[0]();ticks[0]();assert.equal(offline.hidden(),true,'missing frames on an open stream are not reported as a disconnection');
 offline.markDisconnected();ticks[0]();assert.equal(offline.hidden(),false,'a confirmed persistent connection failure remains visible');
 console.log('Video lifecycle passed: immediate retry, selection wake, bounded backoff, static-screen distinction and real failure reporting');
})().catch(error=>{console.error(error);process.exitCode=1;});
