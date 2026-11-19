const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(results){
 let now=10000, serial=0;
 const timers=new Map(), calls=[];
 const context={device:'D',allowed:true,busy:false};
 const sandbox={module:{exports:{}},AbortController,console,
  setTimeout(fn,ms){const id=++serial;timers.set(id,{fn,at:now+ms});return id;},
  clearTimeout(id){timers.delete(id);}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'web/foreground.js'),'utf8'),sandbox);
 const controller=new sandbox.module.exports.ForegroundSyncController({
  client:'test',clock:()=>now,context:()=>context,status:()=>{},apply:()=>{},
  request:async body=>{
   calls.push(body);
   if(body.action==='prepare')return {phase:'prepared'};
   if(body.action==='probe')return results.shift()||{phase:'not_found'};
   return {phase:'released'};
  }
 });
 const probes=()=>calls.filter(c=>c.action==='probe');
 async function advance(ms){
  now+=ms;
  for(const [id,timer] of [...timers])if(timer.at<=now){
   timers.delete(id);timer.fn();
  }
  for(let i=0;i<12;i++)await Promise.resolve();
 }
 controller.retarget('D');
 return {controller,context,advance,probes};
}

(async()=>{
 const found={phase:'identified',phone_number:'+12025550123'};
 const second=setup([{phase:'not_found'},found]);
 second.controller.activity('tap-complete');await second.advance(0);
 assert.equal(second.probes().length,1);
 await second.advance(299);assert.equal(second.probes().length,1);
 await second.advance(1);assert.equal(second.probes().length,2);
 await second.advance(1000);assert.equal(second.probes().length,2);
 assert.equal(second.controller.number,found.phone_number);
 assert.equal(second.probes()[1].probe_attempt,2);

 const failed=setup([]);
 failed.controller.activity('tap-complete');
 await failed.advance(0);await failed.advance(300);await failed.advance(300);
 await failed.advance(10000);assert.equal(failed.probes().length,3);
 failed.controller.activity('tap-complete');await failed.advance(0);
 assert.equal(failed.probes()[3].probe_attempt,1);

 const scrolled=setup([]);
 scrolled.controller.activity('tap-complete');await scrolled.advance(0);
 scrolled.controller.activity('scroll');await scrolled.advance(500);
 assert.equal(scrolled.probes().length,1);

 const switched=setup([]);
 switched.controller.activity('tap-complete');await switched.advance(0);
 switched.context.device='E';switched.controller.retarget('E');
 await switched.advance(500);assert.equal(switched.probes().length,1);

 const busy=setup([found]);
 busy.context.busy=true;busy.controller.activity('tap-complete');await busy.advance(0);
 assert.equal(busy.probes().length,0);
 busy.context.busy=false;await busy.controller.tick();
 assert.equal(busy.probes().length,1);

 const first=setup([found]);
 first.controller.activity('tap-complete');await first.advance(0);await first.advance(3000);
 assert.equal(first.probes().length,1);
 console.log('300ms retries, early success, 3-attempt limit, new tap reset, busy queue and stale task cancellation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
