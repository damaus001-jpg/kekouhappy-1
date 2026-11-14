const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'web/viewer.js'),'utf8');
const turns=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};

async function lifecycle(){
 const listeners={},timers=[],runs=[];let closed=0;
 const context=vm.createContext({window:{addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)},
  setTimeout:fn=>timers.push(fn),log(){},nativeVideoAbort:{abort(){}},compatibleVideoAbort:null,
  videoConnection:{promote(){}},videoDiagnostics:{record(){}},startVideoReports(){},
  cancelFrameDraw(){},resumeVideoDraw(){},
  runVideoForever:()=>new Promise(resolve=>runs.push(resolve)),
  pendingFrame:{close(){closed++;}},lastFrame:{close(){closed++;}},videoStopped:false,videoSessionTask:null});
 vm.runInContext(source.slice(source.indexOf('function ensureVideoSession()'),source.indexOf('inputMonitor = new InputHealthMonitor(')),context);
 context.ensureVideoSession();context.ensureVideoSession();assert.equal(runs.length,1);
 listeners.pagehide[0]({persisted:true});assert.equal(closed,2);
 listeners.pageshow[0]({persisted:true});assert.equal(context.videoStopped,false);
 assert.equal(runs.length,1,'restore never starts a second reader while the old task drains');
 runs[0]();await turns();timers.shift()();assert.equal(runs.length,2,'a drained task is replaced after restore');
 listeners.pageshow[0]({persisted:true});assert.equal(runs.length,2,'repeated restore keeps one session');
 listeners.pagehide[0]({persisted:true});runs[1]();await turns();
 assert.equal(context.videoSessionTask,null);
 listeners.pageshow[0]({persisted:true});assert.equal(runs.length,3,'a fully stopped page resumes after BFCache restore');
}

function presentation(){
 let now=1000,id=0;const timers=new Map(),rafs=new Map(),painted=[],closed=[],reasons=[];
 const context=vm.createContext({performance:{now:()=>now},document:{hidden:false},window:{COMPENSATE:false},
  setTimeout:(fn,ms)=>{timers.set(++id,{fn,ms});return id;},clearTimeout:n=>timers.delete(n),
  requestAnimationFrame:fn=>{rafs.set(++id,fn);return id;},cancelAnimationFrame:n=>rafs.delete(n),
  videoConnection:{frame(){},promote(){}},offlineOverlay:{classList:{add(){}}},
  videoDiagnostics:{decoded:0,painted:0,record:r=>reasons.push(r)},
  drawFrame:f=>painted.push(f.id),fitCanvasToViewport(){},redrawWithCurrentRotation(){},log(){},
  frame:n=>({id:n,displayWidth:100,displayHeight:200,close(){closed.push(n);}})});
 vm.runInContext(`let batchManaged=true,batchSelected=true,lastCanvasDrawAt=0,frameCount=0;
 const BACKGROUND_DRAW_INTERVAL_MS=3000,OFFLINE_GRACE_SECS=3;
 let _lastFc=0,_stableSec=0,_nextPliSec=0,_nextRestartSec=0;
 let lastFrame=null,lastFrameLandscape=null,visualRotation=0,_cropSrcW=0,_cropSrcH=0;
 const deviceFrameEl={dataset:{}};
 ${source.slice(source.indexOf('let pendingFrame = null;'),source.indexOf('// The most recent decoded VideoFrame'))}
 ${source.slice(source.indexOf('function drawPending('),source.indexOf('// A static/quiet screen'))}`,context);
 const run=s=>vm.runInContext(s,context);
 run('queueVideoFrame(frame(1))');let raf=rafs.values().next().value;rafs.clear();raf();
 assert.deepEqual(painted,[1]);assert.equal(timers.size,0,'normal rAF cancels its fallback timer');
 run('queueVideoFrame(frame(2));queueVideoFrame(frame(3))');
 assert.ok(closed.includes(2),'superseded decoded frame is released');
 now+=150;const fallback=timers.values().next().value;timers.clear();fallback.fn();
 assert.deepEqual(painted,[1,3],'stalled rAF paints the newest already-decoded frame');
 assert.equal(rafs.size,0);assert.deepEqual(reasons,['paint-timer-fallback']);
 context.document.hidden=true;run('queueVideoFrame(frame(4))');
 now+=150;const hiddenTimer=timers.values().next().value;timers.clear();hiddenTimer.fn();
 assert.deepEqual(painted,[1,3],'hidden pages do not get a foreground repaint loop');
 context.document.hidden=false;run('resumeVideoDraw()');assert.deepEqual(painted,[1,3,4]);
 assert.equal(rafs.size,0,'visibility restore clears the old suspended rAF');
 run('setBatchVideoSelected(false);queueVideoFrame(frame(5))');
 assert.equal(rafs.size,0);assert.equal(timers.values().next().value.ms,3000,'background cadence remains three seconds');
}

function readProgress(){
 let now=0,aborts=0;
 const context=vm.createContext({performance:{now:()=>now},document:{hidden:false},
  videoStopped:false,batchManaged:true,batchSelected:true,lastSourcePackets:null,localReaderRecoveries:[],
  videoDiagnostics:{mode:'hevc',receivedAt:0,record(){}},nativeVideoAbort:{abort(){aborts++;}},
  videoConnection:{state:'streaming',disconnected(){this.state='retrying';},promote(){}}});
 vm.runInContext(source.slice(source.indexOf('function observeSourceProgress('),source.indexOf('function sendVideoReport(')),context);
 context.observeSourceProgress({source_packets:10,source_au_age_ms:0});
 now=6000;context.observeSourceProgress({source_packets:10,source_au_age_ms:6000});
 assert.equal(aborts,0,'static silence is not enough to cancel a stream');
 context.observeSourceProgress({source_packets:11,source_au_age_ms:0});assert.equal(aborts,1,'proven source progress with stalled client cancels only local fetch');
 context.videoConnection.state='streaming';now=7000;
 context.observeSourceProgress({source_packets:12,source_au_age_ms:0});assert.equal(aborts,1,'local recovery is paced');
 now=12000;context.observeSourceProgress({source_packets:13,source_au_age_ms:0});assert.equal(aborts,2);
 context.videoConnection.state='streaming';now=18000;context.observeSourceProgress({source_packets:14,source_au_age_ms:0});
 assert.equal(aborts,2,'at most two local recoveries per minute');
}
(async()=>{await lifecycle();presentation();readProgress();console.log('Video resume passed: BFCache single session, stalled rAF fallback, visibility restore, static-safe bounded local reader recovery');})().catch(error=>{console.error(error);process.exitCode=1;});
