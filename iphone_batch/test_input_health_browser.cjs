const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/input-health-browser-test'),{headless:true});
 const tab=await localJson(port,'/json/new?about:blank','PUT');
 const c=await CDP.connect(tab.webSocketDebuggerUrl);
 try{
  const source=await fs.readFile(path.join(__dirname,'web/input_health.js'),'utf8');
  await c.evaluate(source);
  await c.evaluate(`window.healthCalls=0;window.healthStates=[];window.healthTest=new InputHealthMonitor({
   request:async()=>{healthCalls++;return {ok:true,state:'ready'};},eligible:()=>true,
   changed:s=>healthStates.push(s)
  });healthTest.setActive(true);`);
  await new Promise(resolve=>setTimeout(resolve,100));
  assert(await c.evaluate('healthTest.ready&&healthTest.failures===0&&healthTest.timer!==null'));
  await c.call('Runtime.evaluate',{expression:'healthTest.check(true)',awaitPromise:true});
  assert.equal(await c.evaluate('healthCalls'),2);
  await c.evaluate('healthTest.setActive(false)');
  assert(await c.evaluate('!healthTest.ready&&healthTest.timer===null'));
  console.log('Browser health monitor passed: native timers, initial verification, manual check and cancellation');
 }finally{await c.call('Browser.close').catch(()=>{});c.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
