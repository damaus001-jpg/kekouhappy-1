const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function setup(){
 let now=10000,serial=0,finishRead;
 const timers=new Map(),known=new Map(),calls=[],applied=[];
 const context={device:'D',allowed:true,busy:false};
 const sandbox={module:{exports:{}},AbortController,console,
  setTimeout(fn,ms){const id=++serial;timers.set(id,{fn,at:now+ms});return id;},
  clearTimeout(id){timers.delete(id);}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'web/foreground.js'),'utf8'),sandbox);
 const record={id:'single',phone_number:'+12025550123',messages:[{text:'Only bubble',side:'outgoing'}]};
 const controller=new sandbox.module.exports.ForegroundSyncController({client:'test',clock:()=>now,
  context:()=>context,status:()=>{},apply:value=>applied.push(value),
  request:async body=>{
   calls.push(body);
   if(body.action==='cancel'){known.delete(body.generation);return {phase:'cancelled'};}
   if(body.action==='probe'){
    known.set(body.generation,true);
    return {phase:'identified',phone_number:record.phone_number,conversations:[],next_seconds:.3};
   }
   if(body.action==='tick'){
    if(!known.has(body.generation))return {phase:'awaiting_tap'};
    if(!finishRead)return new Promise(resolve=>{finishRead=resolve;});
    return {phase:'saved',phone_number:record.phone_number,conversations:[record]};
   }
   return {phase:'prepared'};
  }});
 controller.retarget('D');controller.sessionPrepared=true;controller.seekArmed=true;
 async function advance(ms){
  now+=ms;
  for(const [id,timer] of [...timers])if(timer.at<=now){timers.delete(id);timer.fn();}
  for(let i=0;i<20;i++)await Promise.resolve();
 }
 return {controller,context,calls,applied,advance,finish:()=>finishRead({phase:'saved',conversations:[record]}),
  probes:()=>calls.filter(c=>c.action==='probe')};
}

(async()=>{
 const s=setup();
 await s.controller.tick();
 assert.equal(s.controller.number,'+12025550123');
 await s.advance(300);
 const reading=s.controller.tick();
 s.controller.activity('pointer-start');
 s.finish();await reading;
 assert.equal(s.applied.filter(r=>r.phase==='saved').length,0,'cancelled response must not update the reading area');
 s.controller.activity('pointer-end');await s.advance(400);
 await s.controller.tick();
 await s.advance(300);
 assert.equal(s.probes().length,2,'lost backend read state must re-identify the current conversation');
 await s.advance(300);await s.controller.tick();
 assert.equal(s.applied.at(-1).conversations[0].messages.length,1,'single bubble must reach the reading area after recovery');

 const paused=setup();
 paused.controller.number='+12025550123';
 await paused.controller.tick();
 paused.controller.activity('scroll');await paused.advance(1000);
 await paused.controller.tick();
 assert.equal(paused.probes().length,0,'scrolling cancels recovery and keeps reading paused');

 const exhausted=setup();
 exhausted.controller.number='+12025550123';exhausted.controller.probeAttempts=3;
 await exhausted.controller.tick();
 assert.equal(exhausted.controller.number,null,'exhausted recovery must stop using the stale number');
 const count=exhausted.calls.length;
 await exhausted.advance(10000);await exhausted.controller.tick();
 assert.equal(exhausted.calls.length,count,'exhausted recovery must wait for a fresh tap');
 console.log('Cancelled single-bubble reads re-identify and recover; stale results, scrolling and retry limits remain guarded');
})().catch(error=>{console.error(error);process.exitCode=1;});
