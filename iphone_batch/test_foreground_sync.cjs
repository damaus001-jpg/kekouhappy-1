const assert=require('node:assert/strict');
const {ForegroundSyncController}=require('./web/foreground.js');

function setup(){
 let clock=1000;
 const context={device:'one',allowed:true,busy:false},requests=[],responses=[],applied=[],statuses=[];
 const controller=new ForegroundSyncController({client:'test-client',clock:()=>clock,context:()=>context,
  request:(body,signal)=>{
   requests.push({body,signal});
   if(body.action==='cancel')return Promise.resolve({phase:'cancelled'});
   const result=responses.shift();return typeof result==='function'?result():Promise.resolve(result||{phase:'waiting'});
  },apply:result=>applied.push(result),status:(text,paused)=>statuses.push({text,paused})});
 return {controller,context,requests,responses,applied,statuses,advance:ms=>clock+=ms,
  reads:()=>requests.filter(request=>request.body.action==='tick')};
}

(async()=>{
 const first=setup();
 first.responses.push({phase:'identified',phone_number:'+12025550123',conversations:[{id:'saved'}],next_seconds:.3});
 await first.controller.tick();
 assert.equal(first.controller.number,'+12025550123');assert.equal(first.applied.length,1);
 first.controller.activity('scroll');first.advance(100000);await first.controller.tick();
 assert.equal(first.reads().length,1,'phone scrolling stays paused despite elapsed time');
 assert.equal(first.statuses.at(-1).paused,true);
 first.controller.resume();first.advance(300);await first.controller.tick();
 assert.equal(first.reads().length,2,'explicit resume re-arms reading');

 const switching=setup();let resolve;
 switching.responses.push(()=>new Promise(done=>resolve=done));
 const pending=switching.controller.tick();
 switching.context.device='two';await switching.controller.tick();
 assert.equal(switching.reads()[0].signal.aborted,true);
 resolve({phase:'saved',phone_number:'+12025550123',conversations:[{id:'old-device'}]});await pending;
 assert.equal(switching.applied.length,0,'old device result cannot overwrite current conversation');

 const manual=setup();let finish;
 manual.responses.push(()=>new Promise(done=>finish=done));
 const working=manual.controller.tick();manual.context.busy=true;await manual.controller.tick();
 assert.equal(manual.reads()[0].signal.aborted,true,'manual operations cancel in-flight reads');
 finish({phase:'saved',conversations:[{id:'obsolete'}]});await working;
 assert.equal(manual.applied.length,0);
 manual.context.busy=false;manual.controller.activity('pointer-start');manual.advance(10000);await manual.controller.tick();
 assert.equal(manual.reads().length,1,'held pointer never resumes on an idle timer');
 manual.controller.activity('pointer-end');manual.advance(400);await manual.controller.tick();
 assert.equal(manual.reads().length,2);

 const draft=setup();draft.responses.push({phase:'input_paused'});await draft.controller.tick();
 draft.advance(100000);await draft.controller.tick();assert.equal(draft.reads().length,1);
 draft.controller.activity('key');draft.advance(1800);await draft.controller.tick();assert.equal(draft.reads().length,2);
 const held=setup();held.controller.activity('key-state',{keysHeld:true});held.advance(100000);await held.controller.tick();
 assert.equal(held.reads().length,0,'held modifier keys keep automatic tasks paused');
 held.controller.activity('key-state',{keysHeld:false});held.advance(1800);await held.controller.tick();assert.equal(held.reads().length,1);
 const click=setup();click.responses.push({phase:'input_paused'});await click.controller.tick();
 click.controller.activity('pointer-start');click.controller.activity('pointer-end');click.advance(400);await click.controller.tick();
 assert.equal(click.reads().length,2,'a new phone click can recheck a changed conversation after a draft pause');
 console.log('Foreground scheduling passed: identify/cache, persistent scroll pause, explicit resume, cancellation, stale-result rejection, manual input priority and phone draft pause');
})().catch(error=>{console.error(error);process.exitCode=1;});
