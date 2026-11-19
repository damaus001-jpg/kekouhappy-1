const assert = require('node:assert/strict');
const {ForegroundSyncController} = require('./web/foreground.js');

(async()=>{
 let now=10000;
 const calls=[];
 const controller=new ForegroundSyncController({
  client:'test', clock:()=>now, context:()=>({device:'D',allowed:true,busy:false}),
  status:()=>{},apply:()=>{},
  request:async body=>{
   calls.push(body.action);
   if(body.action==='prepare')return {phase:'prepared'};
   if(body.action==='probe')return {phase:'identified',phone_number:'+12025550123',next_seconds:.3};
   return {phase:'waiting',next_seconds:2};
  }
 });
 controller.retarget('D');
 controller.number='+12025550123';
 controller.activity('scroll');
 now+=10000;await controller.tick();
 assert.equal(calls.filter(a=>['probe','tick'].includes(a)).length,0);
 controller.activity('tap-complete');
 await controller.tick();
 assert(calls.includes('probe'));
 now+=400;await controller.tick();
 assert(calls.includes('tick'));
 console.log('Scroll stays paused; next completed tap identifies and reads again');
})().catch(error=>{console.error(error);process.exitCode=1;});
