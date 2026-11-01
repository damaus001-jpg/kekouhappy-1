const assert=require('node:assert/strict');
const PointerInput=require('./web/pointer_input.js');
const {WheelInput}=PointerInput;
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function make(send,enabled=()=>true){
 const sent=[],timers=new Map();let id=0;
 const pointer=new PointerInput(send|| (async payload=>sent.push(payload)));
 const wheel=new WheelInput(pointer,{bounds:()=>({left:0,top:0,width:400,height:1000}),
  coords:p=>({x:p.clientX,y:p.clientY}),enabled,
  setTimer:(fn,ms)=>{assert.equal(ms,120);timers.set(++id,fn);return id;},clearTimer:key=>timers.delete(key)});
 const event=(deltaY,extra={})=>({deltaY,deltaMode:0,preventDefault(){this.prevented=true;},...extra});
 const finish=()=>{for(const fn of [...timers.values()])fn();};
 return {sent,pointer,wheel,event,finish};
}
(async()=>{
 let app=make();const down=app.event(100);app.wheel.handle(down);await app.pointer.idle();
 assert(down.prevented);assert.equal(app.sent[0].y,750);assert.equal(app.sent[1].y,650);
 assert.equal(app.sent.length,2,'A stationary finger waits without scrolling by itself');
 app.finish();await app.pointer.idle();assert.deepEqual(app.sent[2],{type:'release',x:200,y:650,settle:true});
 app.finish();await app.pointer.idle();assert.equal(app.sent.length,3,'Stop must be idempotent');
 app=make();app.wheel.handle(app.event(-100));await app.pointer.idle();assert.equal(app.sent[1].y,350);app.wheel.stop();await app.pointer.idle();
 app=make();app.wheel.handle(app.event(3,{deltaMode:1}));await app.pointer.idle();assert.equal(app.sent[1].y,696);app.wheel.stop();await app.pointer.idle();
 app=make();app.wheel.handle(app.event(2));app.wheel.handle(app.event(2));assert.equal(app.sent.length,0,'Tiny deltas must not generate accidental taps');app.wheel.handle(app.event(2));await app.pointer.idle();assert.equal(app.sent[1].y,744);app.wheel.stop();await app.pointer.idle();
 for(const extra of [{ctrlKey:true},{metaKey:true}]){app=make();assert.equal(app.wheel.handle(app.event(100,extra)),false);assert.equal(app.sent.length,0);}
 app=make(undefined,()=>false);assert.equal(app.wheel.handle(app.event(100)),false);assert.equal(app.sent.length,0);
 const sent=[],acks=[];app=make(payload=>{sent.push(payload);return new Promise(resolve=>acks.push(resolve));});
 app.wheel.handle(app.event(100));acks.shift()();await tick();assert.equal(sent[1].y,650);
 app.wheel.handle(app.event(40));assert.equal(app.pointer.queue.length,1);
 app.wheel.stop();acks.shift()();await tick();
 assert.deepEqual(sent[2],{type:'release',x:200,y:650,settle:true},'Stopped wheel must not replay queued motion to 610');
 acks.shift()();await app.pointer.idle();assert.equal(sent.length,3);
 const pending=[],done=[];app=make(payload=>{pending.push(payload);return new Promise(resolve=>done.push(resolve));});
 app.pointer.start({x:1,y:1});app.pointer.end();
 app.wheel.handle(app.event(100));app.wheel.stop();done.shift()();await tick();done.shift()();await app.pointer.idle();
 assert.deepEqual(pending.map(p=>p.type),['contact','release'],'A wheel gesture canceled before dispatch must not tap later');
 console.log('Wheel passed: directions, line units, no accidental taps, no stale queued motion, stop release, control gate; mouse drag keeps native inertia');
})().catch(error=>{console.error(error);process.exitCode=1;});
