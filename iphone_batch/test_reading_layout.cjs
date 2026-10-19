const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
const {ensureBrowser,localJson,CDP}=require('./gpt_browser.cjs');
(async()=>{
 const port=await ensureBrowser(path.join(__dirname,'.device-data/reading-layout-test'),{headless:true});
 const target=await localJson(port,'/json/new?'+encodeURIComponent('http://127.0.0.1:8070/#preview-devices'),'PUT');
 const client=await CDP.connect(target.webSocketDebuggerUrl);
 try{
  for(let i=0;i<50;i++){
   if(await client.evaluate("document.querySelectorAll('.device-entry').length===20"))break;
   await new Promise(resolve=>setTimeout(resolve,100));
  }
  await client.evaluate("document.querySelector('.device-entry').click()");
  for(const width of [1920,1440,1024,820,600]){
   await client.call('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
   await new Promise(resolve=>setTimeout(resolve,100));
   const sizes=await client.evaluate(`(()=>{
    const heading=document.querySelector('.message-heading'),meta=document.querySelector('.reading-heading-meta'),controls=document.querySelector('.reading-heading-controls');
    const elements=['.followup-toggle','#followup-panel','#profile-panel'].map(s=>document.querySelector(s).getBoundingClientRect());
    const peer=document.querySelector('.peer-number').getBoundingClientRect();
    const actions=document.querySelector('.heading-actions').getBoundingClientRect();
    const info=document.querySelector('.reading-meta-info').getBoundingClientRect();
    const metaBounds=meta.getBoundingClientRect();
    return {width:document.querySelector('.work-panel').clientWidth,height:heading.getBoundingClientRect().height,
     metaHeight:meta.getBoundingClientRect().height,controlsHeight:controls.getBoundingClientRect().height,
     actionRightOfPeer:actions.left>=info.right,actionRightGap:Math.abs(metaBounds.right-actions.right),actionCenterDelta:Math.abs((actions.top+actions.bottom-peer.top-peer.bottom)/2),
     controlTops:elements.map(e=>Math.round(e.top)),controlBottoms:elements.map(e=>Math.round(e.bottom))};
   })()`);
   assert(sizes.height<=100,JSON.stringify({width,...sizes}));
   assert(Math.max(...sizes.controlTops)-Math.min(...sizes.controlTops)<=8,JSON.stringify(sizes));
   assert(sizes.controlsHeight<=44,JSON.stringify(sizes));
   assert(sizes.actionRightOfPeer&&sizes.actionCenterDelta<=4,JSON.stringify(sizes));
   assert(sizes.actionRightGap<=1,JSON.stringify(sizes));
   console.log(JSON.stringify({viewport:width,...sizes}));
  }
  await client.call('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await client.evaluate("document.getElementById('profile-panel').open=true");
  await new Promise(resolve=>setTimeout(resolve,100));
  const popup=await client.evaluate(`(()=>{const e=document.querySelector('.profile-body'),r=e.getBoundingClientRect();return {inBody:e.parentElement===document.body,left:r.left,right:r.right,top:r.top,bottom:r.bottom};})()`);
  assert(popup.inBody&&popup.left>=0&&popup.right<=1440&&popup.top>=0&&popup.bottom<=900,JSON.stringify(popup));
  await client.evaluate("document.getElementById('profile-panel').open=false");
  await new Promise(resolve=>setTimeout(resolve,100));
  const screenshot=await client.call('Page.captureScreenshot',{format:'png'});
  const output=path.join(__dirname,'.device-data/diagnostics/reading-toolbar-preview.png');
  await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,Buffer.from(screenshot.data,'base64'));
  console.log('Reading layout passed: at most two rows across five widths, popover remains visible');
 }finally{await client.call('Browser.close').catch(()=>{});client.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
