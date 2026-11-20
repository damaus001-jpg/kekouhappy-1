const assert=require('node:assert/strict');
const {ForegroundSyncController}=require('./web/foreground.js');
(async()=>{
 let finish;
 const applied=[],statuses=[],context={device:'D',allowed:true,busy:false};
 let value={device:'D',read_id:'read',revision:1,updated_at:Date.now()+1000,
  phone_number:'+12025550123',messages:[{text:'First'}]};
 const ctl=new ForegroundSyncController({client:'test',context:()=>context,status:text=>statuses.push(text),apply:r=>applied.push(r),
  request:async body=>body.action==='progress'?{phase:'reading_progress',progress:value}:
   body.action==='tick'?new Promise(resolve=>{finish=resolve;}):{phase:'prepared'}});
 ctl.retarget('D');ctl.sessionPrepared=true;ctl.number=value.phone_number;
 const pending=ctl.tick();
 assert.equal(statuses.length,0,'background polling does not flash a checking/loading label');
 await ctl.pollProgress();
 assert.equal(applied[0].phase,'reading_progress','first body must render while the main read request remains unresolved');
 await ctl.pollProgress();assert.equal(applied.length,1,'same snapshot is not rendered repeatedly');
 value={...value,revision:2,messages:[{text:'Older'},{text:'First'}]};
 await ctl.pollProgress();assert.equal(applied[1].progress.messages.length,2);
 context.device='E';await ctl.pollProgress();assert.equal(applied.length,2,'old-device progress cannot overwrite a new selection');
 context.device='D';finish({phase:'waiting',phone_number:ctl.number});await pending;
 assert.equal(ctl.progressWatch,null);
 assert.equal(statuses.at(-1),'已同步，等待新消息');
 context.busy=true;ctl.beginProgress();value={...value,revision:3};
 await ctl.pollProgress();assert.equal(applied.length,3,'manual capture progress is visible despite the operation busy flag');
 value={...value,revision:4,updated_at:0};await ctl.pollProgress();assert.equal(applied.length,3,'stale capture files are ignored');
 ctl.endProgress();
 console.log('Read progress displays before request completion; manual reads, revisions, stale files and device switches guarded');
})().catch(error=>{console.error(error);process.exitCode=1;});
