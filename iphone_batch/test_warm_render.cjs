const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'web/viewer.js'),'utf8');
const callbacks=new Map(),timers=[],rafs=[],canceled=[];let clock=1000,id=0;
const context=vm.createContext({performance:{now:()=>clock},setTimeout:(f,ms)=>{callbacks.set(++id,f);timers.push({id,ms});return id;},clearTimeout:n=>{canceled.push(n);callbacks.delete(n);},requestAnimationFrame:f=>{callbacks.set(++id,f);rafs.push(id);return id;},cancelAnimationFrame:n=>{canceled.push(n);callbacks.delete(n);}});
vm.runInContext(`let batchManaged=true,batchSelected=false,lastCanvasDrawAt=0,frameCount=0;
const BACKGROUND_DRAW_INTERVAL_MS=3000,OFFLINE_GRACE_SECS=3;
let _lastFc=0,_stableSec=0,_nextPliSec=0,_nextRestartSec=0;
const offlineOverlay={classList:{add(){}}};const painted=[],closed=[];
const videoConnection={frame(){},promote(){}};
function fitCanvasToViewport(){} function redrawWithCurrentRotation(){}
function drawPending(){rafScheduled=false;if(pendingFrame){painted.push(pendingFrame.id);pendingFrame=null;lastCanvasDrawAt=performance.now();}}
${source.slice(source.indexOf('let pendingFrame = null;'),source.indexOf('// The most recent decoded VideoFrame'))}
function frame(id){return {id,close(){closed.push(id);}};}`,context);
const run=s=>vm.runInContext(s,context);
clock=3000;run('queueVideoFrame(frame(1))');assert.equal(rafs.length,0);assert.equal(timers.at(-1).ms,0);
callbacks.get(timers.at(-1).id)();
clock=3010;run('queueVideoFrame(frame(2))');assert.equal(timers.at(-1).ms,2990);
clock=3020;run('queueVideoFrame(frame(3))');assert.equal(timers.length,2);
assert.deepEqual(Array.from(run('closed')),[2]);
run('setBatchVideoSelected(true)');
assert.deepEqual(Array.from(run('painted')),[1,3],'latest warmed frame paints synchronously on selection');
assert.ok(canceled.includes(timers.at(-1).id));
clock=3030;run('queueVideoFrame(frame(4))');assert.equal(rafs.length,1);
callbacks.get(rafs.at(-1))();assert.deepEqual(Array.from(run('painted')),[1,3,4]);
clock=3040;run('queueVideoFrame(frame(5)); setBatchVideoSelected(false)');
assert.ok(canceled.includes(rafs.at(-1)),'hiding cancels the foreground rAF');
clock=3050;run('queueVideoFrame(frame(6)); setBatchVideoSelected(true)');
assert.equal(run('painted.at(-1)'),6,'selection never waits for the background timer or a new frame');
console.log('Warm frame timer, foreground takeover, and frame replacement passed');
