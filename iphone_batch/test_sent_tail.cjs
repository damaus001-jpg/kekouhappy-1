const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');

function setup(results){
 let now=10000,id=0;
 const timers=new Map(),calls=[],applied=[];
 const context={device:'D',allowed:true,busy:false,inputBusy:false};
 const sandbox={module:{exports:{}},AbortController,console,
  setTimeout(fn,ms){const n=++id;timers.set(n,{fn,at:now+ms});return n;},
  clearTimeout(n){timers.delete(n);}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'web/foreground.js'),'utf8'),sandbox);
 const ctl=new sandbox.module.exports.ForegroundSyncController({
  client:'test',clock:()=>now,context:()=>context,apply:r=>applied.push(r),status:()=>{},
  request:async body=>{calls.push(body);return body.action==='sent_tail'?
   results.shift()||{phase:'send_pending'}:{phase:'released'};}
 });
 ctl.retarget('D');ctl.expectSend('+12025550123','Hello');
 async function advance(ms){
  now+=ms;
  for(const [n,t] of [...timers])if(t.at<=now){timers.delete(n);t.fn();}
  for(let i=0;i<12;i++)await Promise.resolve();
 }
 return {ctl,context,applied,advance,checks:()=>calls.filter(c=>c.action==='sent_tail')};
}
(async()=>{
 const ok={phase:'send_saved',after_send:true,phone_number:'+12025550123',conversations:[]};
 const tap=setup([{phase:'send_pending'},ok]);
 tap.ctl.activity('tap-complete');await tap.advance(0);
 assert.equal(tap.checks().length,1);
 await tap.advance(299);assert.equal(tap.checks().length,1);
 await tap.advance(1);assert.equal(tap.checks().length,2);
 await tap.advance(500);assert.equal(tap.checks().length,2);
 assert.equal(tap.applied.length,1);
 assert.equal(tap.checks()[0].expected_text,'Hello');

 const enter=setup([ok]);enter.ctl.activity('send-complete');await enter.advance(0);
 assert.equal(enter.applied.length,2);
 assert.equal(enter.applied[0].phase,'send_acknowledged');
 assert.equal(enter.applied[0].receipt.text,'Hello');
 assert.equal(enter.applied[1].phase,'send_saved');
 const failed=setup([]);failed.ctl.activity('send-complete');await failed.advance(0);
 await failed.advance(300);await failed.advance(300);await failed.advance(500);
 assert.equal(failed.checks().length,3);assert.equal(failed.applied.length,1);
 assert.equal(failed.applied[0].phase,'send_acknowledged','slow verification must not delay the submission bubble');

 const rapid=setup([]);let finish;
 rapid.ctl.request=body=>body.action==='sent_tail'?new Promise(resolve=>{finish=resolve;}):Promise.resolve({phase:'released'});
 rapid.ctl.activity('send-start',{id:'key-one'});
 rapid.ctl.expectSend('+12025550123','Second','paste-two');
 rapid.ctl.activity('send-complete',{id:'key-one'});
 assert.equal(rapid.applied[0].receipt.text,'Hello','send acknowledgement uses the Enter-time body snapshot');
 assert.equal(rapid.ctl.expectedSend.text,'Second','later prepared input is retained');
 rapid.ctl.activity('send-complete',{id:'key-one'});
 assert.equal(rapid.applied.length,1,'duplicate Enter receipts cannot append twice');
 const edited=setup([]);edited.ctl.activity('key',{editing:true});
 edited.ctl.activity('send-complete');await edited.advance(0);
 assert.equal(edited.applied.length,0,'phone edits invalidate the known body until re-read');

 const scroll=setup([]);scroll.ctl.activity('send-complete');await scroll.advance(0);
 scroll.ctl.activity('scroll');await scroll.advance(500);
 assert.equal(scroll.checks().length,1);
 const changed=setup([]);changed.ctl.activity('send-complete');await changed.advance(0);
 changed.context.device='E';changed.ctl.retarget('E');await changed.advance(500);
 assert.equal(changed.checks().length,1);
 console.log('Send click and Enter verification, 300ms retry, 3 attempts, success stop and stale cancellation passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
