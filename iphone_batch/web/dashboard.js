/* A thumbnail wall; the existing viewers remain the only video subscribers. */
class GlobalMonitor {
 constructor({pick, menu, refresh, sort}) {
  Object.assign(this,{pick,menu,refresh,sort});this.visible=true;this.tiles=new Map();this.sequence=0;
  this.grid=document.getElementById('monitor-grid');
  this.section=document.getElementById('global-monitor');
  this.switcher=document.getElementById('current-display-devices');this.switcherSignature='';this.displayOrder=[];
  this.layoutButton=document.getElementById('monitor-layout');
  this.sizeSlider=document.getElementById('monitor-size');this.sizeLabel=document.getElementById('monitor-size-value');
  this.sizes={};for(const mode of ['single','double'])try{const n=Number(localStorage.getItem('monitor-size-'+mode));if(n>=50&&n<=480)this.sizes[mode]=n;}catch{}
  let single=false;try{single=localStorage.getItem('monitor-layout')==='single';}catch{}
  this.setLayout(single,false);
  this.layoutButton.addEventListener('click',()=>this.setLayout(!this.single));
  this.sizeSlider.addEventListener('input',()=>{
   const mode=this.single?'single':'double';this.sizes[mode]=Number(this.sizeSlider.value);
   try{localStorage.setItem('monitor-size-'+mode,String(this.sizes[mode]));}catch{}
   this.updateSize();
  });
  this.resizeObserver=new ResizeObserver(()=>this.updateSize());this.resizeObserver.observe(this.grid);
  document.getElementById('monitor-refresh').addEventListener('click',refresh);
  document.getElementById('monitor-sort').addEventListener('change',event=>sort(event.target.value));
  window.addEventListener('message',event=>this.receive(event));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)this.tick();});
  this.timer=setInterval(()=>this.tick(),250);
  window.addEventListener('pagehide',()=>{clearInterval(this.timer);this.resizeObserver.disconnect();for(const tile of this.tiles.values())this.revoke(tile);});
 }
 setLayout(single,persist=true){
  this.single=single;this.section.dataset.layout=single?'single':'double';this.grid.scrollLeft=0;
  this.layoutButton.textContent=single?'双排显示':'单排显示';this.layoutButton.setAttribute('aria-pressed',String(single));
  if(persist)try{localStorage.setItem('monitor-layout',single?'single':'double');}catch{}
  this.updateSize();
 }
 updateSize(){
  const mode=this.single?'single':'double',gap=parseFloat(getComputedStyle(this.grid).columnGap)||12;
  const preferred=this.sizes[mode]??(this.single?Math.max(50,Math.min(480,(this.grid.clientWidth-gap*4)/5)):160);
  const count=Math.max(1,Math.floor((this.grid.clientWidth+gap)/(preferred+gap)));
  const width=this.single?preferred:Math.max(1,(this.grid.clientWidth-gap*(count-1))/count);
  this.grid.style.setProperty('--monitor-tile-width',width+'px');
  // Preserve the sorted reading order across each visible pair of rows.
  [...this.grid.children].forEach((tile,index)=>{
   tile.style.gridRow=this.single?'':String(Math.floor(index/count)%2+1);
   tile.style.gridColumn=this.single?'':String(Math.floor(index/(count*2))*count+index%count+1);
  });
  this.sizeSlider.value=String(Math.round(preferred));this.sizeLabel.textContent=Math.round(width)+' px';
 }
 openWorkbench(){document.querySelector('main').scrollIntoView({behavior:'smooth',block:'start'});}
 scrollToTop(){document.getElementById('global-monitor').scrollIntoView({behavior:'smooth',block:'start'});}
 revoke(tile){if(tile.url){URL.revokeObjectURL(tile.url);tile.url=null;}}
 render(ordered,cards,sortValue) {
  this.cards=cards;
  this.displayOrder=ordered;
  const connected=new Set(ordered.map(row=>row.device.udid));
  for(const [id,tile] of this.tiles)if(!connected.has(id)){this.revoke(tile);tile.node.remove();this.tiles.delete(id);}
  document.getElementById('monitor-count').textContent=ordered.length+' 台设备 · '+[...this.tiles.values()].filter(tile=>tile.url&&tile.device?.ready).length+' 台已显示 · '+ordered.filter(row=>row.device.ready).length+' 台投屏就绪';
  document.getElementById('monitor-empty').hidden=ordered.length!==0;
  document.getElementById('monitor-sort').value=sortValue;
  const now=Date.now();
  ordered.forEach(({device,index,label,followupCount},position)=>{
   let tile=this.tiles.get(device.udid);
   if(!tile){
    const node=document.createElement('button');node.type='button';node.className='monitor-tile';node.dataset.udid=device.udid;
    const heading=document.createElement('span');heading.className='monitor-tile-heading';
    const flip=document.createElement('span');flip.className='monitor-device-flip';
    const number=document.createElement('strong'),backLabel=document.createElement('strong');number.className='monitor-device-front';backLabel.className='monitor-device-back';backLabel.textContent='待跟进';flip.append(number,backLabel);
    const badge=document.createElement('span');badge.className='monitor-badge';heading.append(flip,badge);
    const screen=document.createElement('span');screen.className='monitor-screen';
    const image=document.createElement('img');image.alt='';image.hidden=true;image.draggable=false;
    const placeholder=document.createElement('span');placeholder.className='monitor-placeholder';screen.append(image,placeholder);
    node.append(heading,screen);
    tile={node,number,flip,backLabel,badge,image,placeholder,nextAt:now+position*1500/Math.max(1,ordered.length),url:null,received:0,pending:null};
    node.addEventListener('click',()=>this.pick(device.udid));
    node.addEventListener('contextmenu',event=>this.menu(event,tile.device,tile.index));
    this.tiles.set(device.udid,tile);
   }
   tile.device=device;tile.index=index;
   tile.node.classList.toggle('monitor-selected',device.udid===this.selected);
   const frame=cards.get(device.udid)?.frame;
   if(tile.frame!==frame){tile.frame=frame;tile.pending=null;tile.received=0;tile.firstRequestAt=0;this.revoke(tile);tile.image.hidden=true;tile.image.removeAttribute('src');}
   tile.number.textContent='设备 '+label.number;
   const hasFollowup=followupCount>0||label.followup===true;
   tile.flip.classList.toggle('has-followup',hasFollowup);
   tile.backLabel.hidden=!hasFollowup;
   const count=device.notifications?.card_count??device.notifications?.items?.length??0;
   tile.badge.textContent=count?String(count):'';tile.badge.hidden=!count;
   tile.node.title=device.name+' · '+device.udid.slice(-8)+(followupCount?' · 待跟进 '+followupCount:label.followup?' · 待跟进':'')+' · 点击进入操作；右键管理设备';
   tile.node.setAttribute('aria-label','设备 '+label.number+'，'+(device.ready?'点击进入操作':device.error||'正在准备投屏'));
   this.updateState(tile,now);this.grid.append(tile.node);
  });
  this.updateSize();
  this.syncDeviceSwitcher();
 }
 syncDeviceSwitcher(){
  if(!this.switcher)return;
  const entries=this.displayOrder.filter(({device})=>{
   const tile=this.tiles.get(device.udid);return !!(tile?.url&&device.ready);
  });
  const signature=[this.selected||'',...entries.map(({device,label})=>device.udid+':'+label.number)].join('|');
  if(signature===this.switcherSignature)return;
  const newSmsButton=document.getElementById('new-sms-task');
  this.switcherSignature=signature;this.switcher.replaceChildren();this.switcher.hidden=false;
  if(newSmsButton)this.switcher.append(newSmsButton);
  for(const {device,label} of entries){
   const button=document.createElement('button');button.type='button';button.className='current-display-device';
   button.textContent=label.number;button.title='切换到 '+label.number;button.setAttribute('aria-pressed',String(device.udid===this.selected));
   if(device.udid===this.selected)button.classList.add('current');
   button.addEventListener('click',()=>this.pick(device.udid));this.switcher.append(button);
  }
 }
 updateState(tile,now){
  const ready=tile.device.ready,stale=tile.received&&now-tile.received>10000;
  const waiting=ready&&!tile.received&&tile.firstRequestAt&&now-tile.firstRequestAt>15000;
  tile.node.classList.toggle('monitor-stale',!!stale||tile.streamState==='retrying'||!ready);
  const alert=tile.device.enabled!==false&&((!ready&&!tile.device.reconnecting&&!tile.device.trust_pending)||!!stale||tile.streamState==='retrying');
  tile.node.classList.toggle('monitor-offline-alert',!!alert);
  tile.placeholder.hidden=!!tile.url;
  const status=tile.device.enabled===false?'已断开，右键选择“接入此台”':tile.device.trust_pending?'正在检查并修复信任，如手机弹窗请确认':tile.device.reconnecting?(tile.device.reconnect_stage==='trusting'?'正在检查并修复信任，如手机弹窗请确认':'正在重新连接，请稍候'):!ready?tile.device.error||tile.device.reconnect_error||'正在准备手机画面，请稍候':stale?'更新中断，保留上次画面':tile.streamState==='retrying'?'画面重连中':waiting?'暂未收到手机画面，可右键重新连接此设备':tile.received?'画面已显示':'正在等待手机画面';
  tile.placeholder.textContent=status;
  tile.node.setAttribute('aria-label',tile.number.textContent+'，'+status+'；点击进入操作，右键管理设备');
 }
 tick(){
  if(!this.visible||document.hidden||!this.cards)return;
  const now=Date.now();
  for(const [id,tile] of this.tiles){
   this.updateState(tile,now);
   if(!tile.device.ready||!tile.frame||now<tile.nextAt)continue;
   if(tile.pending&&now-tile.requested<6000)continue;
   const card=this.cards.get(id);if(card?.frame!==tile.frame)continue;
   tile.pending='monitor-'+(++this.sequence);tile.requested=now;tile.nextAt=now+1500;if(!tile.firstRequestAt)tile.firstRequestAt=now;
   card.frame.contentWindow.postMessage({type:'monitor-snapshot',id:tile.pending},card.origin);
  }
 }
 receive(event){
  if(event.data?.type!=='monitor-snapshot-result'||!this.visible)return;
  for(const [id,tile] of this.tiles){
   const card=this.cards?.get(id);
   if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin||event.data.id!==tile.pending)continue;
   tile.pending=null;tile.streamState=event.data.state;
   const blob=event.data.image;
   if(!(blob instanceof Blob)||blob.type!=='image/jpeg'||blob.size>1024*1024)return;
   const previous=tile.url;tile.url=URL.createObjectURL(blob);tile.image.src=tile.url;tile.image.hidden=false;
   if(previous)URL.revokeObjectURL(previous);
   this.syncDeviceSwitcher();
   tile.received=Date.now();this.updateState(tile,tile.received);return;
  }
 }
}


const cards=new Map();let active=null;let busy=false;let latest=[];let controlPaused=false;
const phoneScaleInput=document.createElement('input'),phoneScaleValue=document.createElement('output');
phoneScaleInput.type='range';phoneScaleInput.id='phone-screen-size';phoneScaleInput.min='50';phoneScaleInput.max='130';phoneScaleInput.step='5';
let phoneScreenScale=100;try{const saved=Number(localStorage.getItem('phone-screen-size'));if(saved>=50&&saved<=130)phoneScreenScale=saved;}catch{}
phoneScaleInput.value=String(phoneScreenScale);phoneScaleValue.value=phoneScreenScale+'%';phoneScaleValue.textContent=phoneScreenScale+'%';
const workbench=document.querySelector('main'),phoneViewport=document.getElementById('selected'),phonePanel=document.querySelector('.phone-panel');
function syncPhoneScaleLayout(){
 workbench.style.height=Math.round(window.innerHeight*phoneScreenScale/100)+'px';
 schedulePhoneLayout();
}
function applyPhoneScale(){
 phoneScreenScale=Number(phoneScaleInput.value);phoneScaleValue.value=phoneScreenScale+'%';phoneScaleValue.textContent=phoneScaleValue.value;
 try{localStorage.setItem('phone-screen-size',String(phoneScreenScale));}catch{}
 syncPhoneScaleLayout();
}
phoneScaleInput.addEventListener('input',applyPhoneScale);
const phoneSizeLabel=document.createElement('label');phoneSizeLabel.className='phone-screen-size-control';phoneSizeLabel.title='调整实时画面默认大小，仍随窗口空间自适应';phoneSizeLabel.append('画面大小 ',phoneScaleInput,phoneScaleValue);
document.querySelector('.phone-panel .section-title h2').after(phoneSizeLabel);
const phoneDisplayTools=document.createElement('div');phoneDisplayTools.className='phone-display-tools';
phoneSizeLabel.after(phoneDisplayTools);
phoneDisplayTools.append(phoneSizeLabel,document.querySelector('.phone-panel .phone-actions'));
let phoneLayoutFrame=null;
function schedulePhoneLayout(){
 if(phoneLayoutFrame===null)phoneLayoutFrame=requestAnimationFrame(updatePhoneLayout);
}
function updatePhoneLayout(){
 phoneLayoutFrame=null;
 const aspect=cards.get(active)?.videoAspect||9/19.5;
 if(window.innerWidth<=820){
  const titleHeight=phonePanel.querySelector('.section-title').getBoundingClientRect().height;
  const screenHeight=Math.ceil(Math.max(1,phoneViewport.clientWidth-18)/aspect+18);
  const height=Math.ceil(titleHeight+8+screenHeight)+'px';
  if(phonePanel.style.height!==height)phonePanel.style.height=height;
  return;
 }
 phonePanel.style.removeProperty('height');
 if(!phoneViewport.clientHeight)return;
 // Reserve the reading panel's minimum width while allowing the live screen
 // to grow with the slider instead of stopping at a fixed 30vw/440px ceiling.
 const sideRailWidth=72;
 const limit=Math.max(270,window.innerWidth-440-sideRailWidth);
 // The embedded stage reserves 12px padding and 4px frame clearance;
 // #selected adds a 2px border. Use source dimensions, never scaled width.
 const fitted=Math.max(0,phoneViewport.clientHeight-16)*aspect+18;
 const width=Math.ceil(Math.max(220,Math.min(limit,fitted))+sideRailWidth)+'px';
 if(workbench.style.getPropertyValue('--phone-column-width')!==width)workbench.style.setProperty('--phone-column-width',width);
}
const phoneLayoutObserver=new ResizeObserver(schedulePhoneLayout);
phoneLayoutObserver.observe(workbench);phoneLayoutObserver.observe(phoneViewport);
window.addEventListener('pagehide',()=>{phoneLayoutObserver.disconnect();if(phoneLayoutFrame!==null)cancelAnimationFrame(phoneLayoutFrame);});
window.addEventListener('resize',syncPhoneScaleLayout);
syncPhoneScaleLayout();
let selectionRevision=0;
let controlOwner=null;
const devicePreview=location.hash==='#preview-devices';
const globalMonitor=typeof GlobalMonitor==='function'?new GlobalMonitor({
 pick:udid=>select(udid),menu:(event,device,index)=>showDeviceMenu(event,device,index),
 refresh:()=>refreshDevices(),sort:value=>{sortControl.value=value;sortControl.dispatchEvent(new Event('change'));}
}):null;
if(globalMonitor){
 const back=document.createElement('button');back.id='monitor-back';back.type='button';back.className='secondary monitor-back';back.textContent='↑ 设备列表';
 const page=document.scrollingElement||document.documentElement;
 let navDestination='devices';
 const updateNav=()=>{back.dataset.destination=navDestination;back.textContent=navDestination==='screen'?'↓ 当前画面':'↑ 设备列表';};
 back.addEventListener('click',()=>{
  const goToScreen=back.dataset.destination==='screen';
  navDestination=goToScreen?'devices':'screen';updateNav();
  const top=goToScreen?Math.max(0,page.scrollHeight-window.innerHeight):0;
  window.scrollTo(0,top);
 });
 const title=document.querySelector('.phone-panel .section-title h2'),titleBox=document.createElement('div');
 titleBox.className='phone-title-container';title.before(titleBox);titleBox.append(title,back);
 const toolsToggle=document.createElement('button');toolsToggle.id='phone-display-tools-toggle';toolsToggle.type='button';toolsToggle.className='secondary phone-display-tools-toggle';
 let toolsCollapsed=false;try{toolsCollapsed=localStorage.getItem('phone-display-tools-collapsed')==='true';}catch{}
 const syncToolsToggle=()=>{
  phoneDisplayTools.hidden=toolsCollapsed;toolsToggle.textContent=toolsCollapsed?'展开工具':'收起工具';
  toolsToggle.title=toolsCollapsed?'展开画面大小、主页、截屏和设备信息':'折叠画面大小、主页、截屏和设备信息';
  toolsToggle.setAttribute('aria-expanded',String(!toolsCollapsed));
 };
 toolsToggle.addEventListener('click',()=>{
  toolsCollapsed=!toolsCollapsed;try{localStorage.setItem('phone-display-tools-collapsed',String(toolsCollapsed));}catch{}
  syncToolsToggle();schedulePhoneLayout();
 });
 titleBox.append(toolsToggle);syncToolsToggle();
 const syncNav=()=>{
  const maxTop=Math.max(0,page.scrollHeight-window.innerHeight);
  if(maxTop>1)navDestination=page.scrollTop>=maxTop/2?'devices':'screen';
  updateNav();
 };
 window.addEventListener('scroll',syncNav,{passive:true});window.addEventListener('resize',syncNav);syncNav();
}
function showGlobalMonitor(){
 closeDeviceMenu();globalMonitor?.scrollToTop();
}
let refreshingDevices=false,deviceRefreshQueued=false;
const refreshDevicesButton=document.getElementById('refresh-devices');
function syncDeviceRefreshControls(){
 if(!refreshDevicesButton)return;
 refreshDevicesButton.disabled=refreshingDevices;
 refreshDevicesButton.textContent=refreshingDevices?'…':deviceRefreshQueued?'↻…':'↻';
 refreshDevicesButton.title=deviceRefreshQueued?'已安排刷新，等待当前操作结束':refreshingDevices?'正在重新检测 USB 手机':'重新检测 USB 手机';
 refreshDevicesButton.setAttribute('aria-busy',String(refreshingDevices||deviceRefreshQueued));
 if(deviceRefreshQueued&&!busy&&!workspaceBusy&&!refreshingDevices)void refreshDevices();
}
async function deviceRequest(url,options,timeout=15000){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
 try{
  const response=await fetch(url,{...options,signal:controller.signal});
  const result=await response.json();if(!response.ok)throw Error(result.error||'设备操作失败');
  return result;
 }catch(error){if(error.name==='AbortError')throw Error('设备操作超时，请检查连接后刷新重试。');throw error;}
 finally{clearTimeout(timer);}
}
async function refreshDevices(){
 if(refreshingDevices)return;
 if(devicePreview){render(previewDevices,previewSelection);notice('预览模式：已刷新模拟设备');return;}
 if(busy||workspaceBusy){
  deviceRefreshQueued=true;syncDeviceRefreshControls();
  notice('当前操作尚未结束，已安排设备刷新；结束后自动检查连接。');return;
 }
 deviceRefreshQueued=false;refreshingDevices=true;syncDeviceRefreshControls();
 notice('正在重新检测 USB 并检查当前手机连接…');
 try{
  const result=await deviceRequest('/api/devices/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  await refresh();
  if(active&&controlOwner!==active&&latest.some(d=>d.udid===active&&d.ready)){
   const selectedState=await deviceRequest('/api/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({udid:active})});
   controlOwner=selectedState.active;render(latest,selectedState.selected??selectedState.active,controlOwner);
  }
  notice('已重新检测 USB：当前识别到 '+result.count+' 台手机。');
  const card=cards.get(active);
  if(card?.frame&&controlOwner===active)card.frame.contentWindow.postMessage({type:'input-recover'},card.origin);
 }catch(error){notice(error.message);}
 finally{refreshingDevices=false;syncDeviceRefreshControls();}
}
refreshDevicesButton?.addEventListener('click',refreshDevices);
const phoneHomeButton=document.getElementById('phone-home');
const phoneScreenshotButton=document.getElementById('phone-screenshot');
const screenshotDialog=document.getElementById('phone-screenshot-dialog');
const screenshotStatus=document.getElementById('phone-screenshot-status');
const screenshotNative=document.getElementById('screenshot-native');
const screenshotComputer=document.getElementById('screenshot-computer');
const screenshotDownload=document.getElementById('screenshot-download');
let screenshotRequest=null,screenshotTimer=null,screenshotSequence=0;
let screenshotDownloadUrl=null,screenshotDownloadName='',screenshotUseDownloads=false;
try{screenshotUseDownloads=localStorage.getItem('screenshot-use-downloads')==='true';}catch{}
function clearScreenshotDownload(){
 if(screenshotDownloadUrl)URL.revokeObjectURL(screenshotDownloadUrl);
 screenshotDownloadUrl=null;screenshotDownloadName='';screenshotDownload.hidden=true;
}
function downloadScreenshot(){
 if(!screenshotDownloadUrl)return;
 const link=document.createElement('a');link.href=screenshotDownloadUrl;link.download=screenshotDownloadName;
 document.body.appendChild(link);link.click();link.remove();
}
screenshotDownload.addEventListener('click',downloadScreenshot);
function offerScreenshotDownload(blob,filename,message){
 clearScreenshotDownload();screenshotDownloadUrl=URL.createObjectURL(blob);screenshotDownloadName=filename;
 screenshotDownload.hidden=false;downloadScreenshot();screenshotStatus.textContent=message;
}
function rememberScreenshotWriteDenied(error){
 if(!['NotAllowedError','SecurityError','NotSupportedError'].includes(error?.name))return;
 screenshotUseDownloads=true;
 try{localStorage.setItem('screenshot-use-downloads','true');}catch{}
}
function syncScreenshotActions(){
 const available=!devicePreview&&latest.some(d=>d.udid===active&&d.ready);
 phoneScreenshotButton.disabled=!!screenshotRequest||!available;
 screenshotComputer.disabled=!!screenshotRequest||!available;
 screenshotNative.disabled=!!screenshotRequest||!available||controlOwner!==active||busy||workspaceBusy||controlPaused;
 screenshotNative.title=screenshotNative.disabled&&!screenshotRequest?'请先接入当前手机，等待控制连接就绪':'';
}
function clearPhoneScreenshot(){
 clearTimeout(screenshotTimer);screenshotTimer=null;screenshotRequest=null;
 clearScreenshotDownload();
 syncScreenshotActions();
}
document.getElementById('phone-screenshot-close').addEventListener('click',()=>screenshotDialog.close());
screenshotDialog.addEventListener('close',clearPhoneScreenshot);
phoneScreenshotButton?.addEventListener('click',()=>{
 const device=latest.find(d=>d.udid===active&&d.ready),card=cards.get(active);
 if(devicePreview||screenshotRequest||!device||!card?.frame)return;
 window.ForegroundSync?.activity('manual');
 clearPhoneScreenshot();
 screenshotDialog.dataset.device=active;
 document.getElementById('phone-screenshot-title').textContent='设备 '+deviceLabel(device,latest.indexOf(device)).number+' · 截屏';
 screenshotStatus.textContent=window.showSaveFilePicker&&!screenshotUseDownloads?'请选择截屏方式。':'当前浏览器使用下载保存；如需选择文件夹，请开启浏览器“下载前询问保存位置”。';
 screenshotDialog.showModal();
});
function requestScreenshot(mode){
 syncScreenshotActions();
 if(!screenshotDialog.open||screenshotDialog.dataset.device!==active||
    (mode==='native'?screenshotNative:screenshotComputer).disabled)return;
 const card=cards.get(active),device=latest.find(d=>d.udid===active);
 if(!card?.frame||!device)return;
 clearScreenshotDownload();
 window.ForegroundSync?.activity('manual');
 const stamp=new Date(),z=n=>String(n).padStart(2,'0');
 const filename='设备'+deviceLabel(device,latest.indexOf(device)).number+'_'+stamp.getFullYear()+z(stamp.getMonth()+1)+z(stamp.getDate())+'_'+z(stamp.getHours())+z(stamp.getMinutes())+z(stamp.getSeconds())+'.png';
 const request=screenshotRequest={id:'screenshot-'+(++screenshotSequence),udid:active,frame:card.frame,origin:card.origin,mode,filename};
 syncScreenshotActions();
 screenshotStatus.textContent=mode==='native'?'正在发送手机截屏指令…':'正在截取实时画面…';
 // Invoke the picker during the click's user activation. Store a settled result
 // immediately so cancellation cannot create an unhandled rejection.
 if(mode==='computer'&&window.showSaveFilePicker&&!screenshotUseDownloads){
  try{request.file=window.showSaveFilePicker({suggestedName:filename,types:[{description:'PNG 图片',accept:{'image/png':['.png']}}]}).then(handle=>({handle}),error=>({error}));}
  catch(error){request.file=Promise.resolve({error});}
 }
 screenshotTimer=setTimeout(()=>{
  if(screenshotRequest!==request)return;
  clearPhoneScreenshot();screenshotStatus.textContent=mode==='native'?'未收到截屏结果，请先查看手机相册，再决定是否重试。':'截屏超时，请确认实时画面连接后重试。';
 },16000);
 card.frame.contentWindow.postMessage({type:mode==='native'?'native-screenshot':'canvas-screenshot',id:request.id},card.origin);
}
screenshotNative.addEventListener('click',()=>requestScreenshot('native'));
screenshotComputer.addEventListener('click',()=>requestScreenshot('computer'));
async function finishScreenshot(event){
 const request=screenshotRequest;
 if(!request||event.source!==request.frame.contentWindow||event.origin!==request.origin||event.data.id!==request.id)return;
 if(event.data.type!==(request.mode==='native'?'native-screenshot-result':'canvas-screenshot-result'))return;
 if(request.received)return;
 request.received=true;
 if(active!==request.udid||cards.get(active)?.frame!==request.frame){screenshotDialog.close();return;}
 clearTimeout(screenshotTimer);screenshotTimer=null;
 const current=()=>screenshotRequest===request&&screenshotDialog.open&&active===request.udid;
 try{
  if(event.data.error)throw Error(event.data.error);
  if(request.mode==='native'){
   if(event.data.ok!==true)throw Error('截屏指令未完成，请检查手机连接。');
   screenshotStatus.textContent='截屏指令已发送，请在这台手机的“照片”中查看。';return;
  }
  const blob=event.data.image;
  if(!(blob instanceof Blob)||blob.type!=='image/png'||!blob.size||blob.size>24*1024*1024)throw Error('截图数据无效，请重试。');
  const signature=new Uint8Array(await blob.slice(0,8).arrayBuffer());
  if(signature.length!==8||![137,80,78,71,13,10,26,10].every((value,index)=>signature[index]===value))throw Error('截图不是有效的 PNG 图片，请重试。');
  if(!current())return;
  if(request.file){
   screenshotStatus.textContent='请选择电脑上的保存位置…';
   const {handle,error}=await request.file;
   if(!current())return;
   if(error?.name==='AbortError')throw error;
   let writable;
   try{
    if(error)throw error;
    writable=await handle.createWritable();
    if(!current()){await writable.abort();return;}
    await writable.write(blob);await writable.close();
    if(current())screenshotStatus.textContent='已保存到电脑：'+handle.name;
   }catch(writeError){
    if(writable)await writable.abort().catch(()=>{});
    if(!current())return;
    rememberScreenshotWriteDenied(writeError);
    offerScreenshotDownload(blob,handle?.name||request.filename,'直接写入失败，已改用浏览器下载完整图片。保存位置以浏览器设置为准；如需选择文件夹，请开启“下载前询问保存位置”。未出现下载时，可点击下方按钮重试。');
   }
  }else{
   offerScreenshotDownload(blob,request.filename,'已交给浏览器下载；保存位置以浏览器设置为准。如需选择文件夹，请开启“下载前询问保存位置”。未出现下载时，可点击下方按钮重试。');
  }
 }catch(error){if(current())screenshotStatus.textContent=error.name==='AbortError'?'已取消保存。':(error.message||'截屏失败，请重试。');}
 finally{if(screenshotRequest===request){screenshotRequest=null;syncScreenshotActions();}}
}
phoneHomeButton?.addEventListener('click',()=>{
 if(!active||controlOwner!==active||busy||workspaceBusy||controlPaused||devicePreview)return;
 window.ForegroundSync?.activity('manual');
 const card=cards.get(active);
 if(!card?.frame){notice('手机画面尚未连接，请稍后重试');return;}
 card.frame.contentWindow.postMessage({type:'device-home'},card.origin);
});
window.addEventListener('message',event=>{
 if(event.data?.type==='native-screenshot-result'||event.data?.type==='canvas-screenshot-result'){void finishScreenshot(event);return;}
 if(event.data?.type==='video-dimensions'){
  const {width,height}=event.data;
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0||width>16384||height>16384)return;
  for(const [udid,card] of cards){
   if(!card.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)continue;
   card.videoAspect=width/height;if(udid===active)schedulePhoneLayout();return;
  }
  return;
 }
 if(event.data?.type==='manual-input-result'){
  const card=cards.get(active);
  if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
  if(event.data.ok===false&&typeof event.data.message==='string'){
   const device=latest.find(row=>row.udid===active);
   const label=device?deviceLabel(device,latest.indexOf(device)).number:'';
   const message=event.data.message.slice(0,300);
   notice('设备 '+label+'：'+message);
   if(card.connectionNotice){card.connectionNotice.hidden=false;card.connectionNotice.textContent=message;}
  }
  return;
 }
 if(event.data?.type==='clipboard-paste-result'){
  const card=cards.get(active);
  if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
  if(typeof event.data.message==='string')notice(event.data.message.slice(0,300));
  return;
 }
 if(event.data?.type==='input-health-result'){
  const card=cards.get(active);
  if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
  const state=event.data;
  card.inputReady=state.ready===true;
  card.controlReady=state.ready===true;
  syncWorkspaceControls();
  if(card.connectionNotice){
   card.connectionNotice.hidden=state.ready===true||state.state==='inactive';
   card.connectionNotice.textContent=state.state==='unavailable'?'控制连接不可用，点击设备列表刷新重试':'控制连接检查与恢复中…';
  }
  if(state.manual&&state.ready)notice('当前设备输入连接'+(state.recovered?'已重新建立':'检查通过')+'，请确认实际操控效果。');
  if(state.ready&&state.prewarmed)notice('已切换设备，输入连接已准备');
  return;
 }
 if(event.data?.type!=='device-home-result')return;
 const card=cards.get(active);
 if(!card?.frame||event.source!==card.frame.contentWindow||event.origin!==card.origin)return;
 notice(event.data.ok?'已请求返回手机主页':event.data.error||'返回手机主页失败，请检查手机连接');
});
let revealingDeveloperMode=false;
let developerModeFeedbackDevice=null;
const revealDeveloperModeButton=document.getElementById('reveal-developer-mode');
const developerModeStatus=document.getElementById('developer-mode-status');
const deviceSetupLabel=document.getElementById('device-setup-device');
function syncDeveloperModeButton(){
 const selectedDevice=latest.find(device=>device.udid===active);
 if(deviceSetupLabel){deviceSetupLabel.textContent=selectedDevice?'设备'+deviceLabel(selectedDevice,latest.indexOf(selectedDevice)).number:'';deviceSetupLabel.hidden=!selectedDevice;}
 if(!revealDeveloperModeButton)return;
    revealDeveloperModeButton.disabled=!active||latest.find(d=>d.udid===active)?.enabled===false||latest.find(d=>d.udid===active)?.readonly===true||busy||workspaceBusy||revealingDeveloperMode||devicePreview;
 revealDeveloperModeButton.textContent=revealingDeveloperMode?'正在显示入口…':'显示开发者入口';
 if(developerModeFeedbackDevice!==active){
  developerModeFeedbackDevice=active;
  developerModeStatus.textContent=active?'仅显示当前手机的设置入口；请在手机上手动开启开发者模式：设置内搜索“开发者”或“Developer”，若找不到，就点击本弹窗的“显示开发者入口”按钮后间隔10秒再搜索。':'选中手机后，请在手机上手动开启开发者模式：设置内搜索“开发者”或“Developer”，若找不到，就点击本弹窗的“显示开发者入口”按钮后间隔10秒再搜索。';
 }
}
revealDeveloperModeButton?.addEventListener('click',async()=>{
 if(!active||busy||workspaceBusy||revealingDeveloperMode||devicePreview)return;
 const device=active;
 const row=latest.find(d=>d.udid===device);
 const label=row?deviceLabel(row,latest.indexOf(row)).number:device.slice(-8);
 revealingDeveloperMode=true;syncDeveloperModeButton();
 developerModeStatus.textContent='正在为设备 '+label+' 显示入口…';
 try{
  const response=await fetch('/api/developer-mode/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device})});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'显示入口失败，请检查手机连接后重试');
  if(active===device)developerModeStatus.textContent='设备 '+label+'：'+result.message;
 }catch(error){if(active===device)developerModeStatus.textContent='设备 '+label+'：'+error.message;}
 finally{revealingDeveloperMode=false;syncDeveloperModeButton();}
});
let previewSelection=null;
const previewDevices=Array.from({length:20},(_,i)=>({
 udid:'preview-device-'+(i+1),number:String(i+1).padStart(2,'0'),name:'iPhone '+(i+1),
 followup:[2,5,10,13].includes(i),
 ready:false,port:8080+i,
 notifications:{card_count:[3,0,12,1,0,6,0,2,0,0,5,0,8,0,1,0,0,4,0,99][i],last_checked:'2026-10-18T12:00:00Z'}
}));
let editingDevice=null;
let previewLoadedDevice=null;
const sortControl=document.getElementById('device-sort');
const followupControl=document.getElementById('device-followup');
const sortStorageKey='iphone-device-sort-v2:'+(devicePreview?'preview':'device');
sortControl.value='number';
try{const saved=localStorage.getItem(sortStorageKey);if(['number','unread','followup'].includes(saved))sortControl.value=saved;}catch{}
sortControl.addEventListener('change',()=>{
 try{localStorage.setItem(sortStorageKey,sortControl.value);}catch{}
 render(latest,active);
});
let deviceMenuTarget=null;
const accessRequests=new Set();
const accessNotices=new Map();
const reconnectRequests=new Set(),reconnectNotices=new Map();
const deviceMenu=document.getElementById('device-context-menu');
function closeDeviceMenu(){deviceMenu.hidden=true;deviceMenuTarget=null;}
function showDeviceMenu(event,device,index){
 event.preventDefault();deviceMenuTarget={device,index};deviceMenu.hidden=false;
 const connectionButton=document.getElementById('device-context-connection'),readonlyButton=document.getElementById('device-context-readonly');
 connectionButton.textContent=device.enabled===false?'接入此台':'断开此台：停止画面和操作';
 readonlyButton.textContent=device.readonly?'允许操作':'仅监看：锁定鼠标和键盘';
 connectionButton.disabled=readonlyButton.disabled=devicePreview||workspaceBusy||busy||accessRequests.has(device.udid)||device.trust_pending||device.reconnecting;
 const reconnectButton=document.getElementById('device-context-reconnect');
 reconnectButton.disabled=device.enabled===false||devicePreview||device.trust_pending||device.reconnecting||reconnectRequests.has(device.udid)||workspaceBusy||busy;
 reconnectButton.textContent=device.reconnecting?'正在重新连接…':'重新连接此设备';
 reconnectButton.title='按需修复此台信任连接，再恢复画面与操控；手机若出现信任提示，请完成确认。';
 const rebootButton=document.getElementById('device-context-reboot');
 rebootButton.disabled=reconnectButton.disabled||device.readonly;
 rebootButton.textContent=device.reconnecting&&device.reconnect_operation==='reboot'?'正在重启手机…':'重启此手机…';
 rebootButton.title='重启这台手机，开机后需要在手机输入密码解锁。';
 const followup=deviceLabel(device,index).followup;
 document.getElementById('device-context-followup').setAttribute('aria-checked',String(followup));
 document.getElementById('device-context-none').setAttribute('aria-checked',String(!followup));
 const bounds=deviceMenu.getBoundingClientRect();
 deviceMenu.style.left=Math.max(4,Math.min(event.clientX,window.innerWidth-bounds.width-4))+'px';
 deviceMenu.style.top=Math.max(4,Math.min(event.clientY,window.innerHeight-bounds.height-4))+'px';
 document.getElementById('device-context-edit').focus();
}
async function changeDeviceAccess(device,changes){
 if(devicePreview||workspaceBusy||busy||accessRequests.has(device.udid))return;
 accessRequests.add(device.udid);
 const label=deviceLabel(device,latest.indexOf(device)).number;
 const action='enabled' in changes?(changes.enabled?'接入':'断开'):(changes.readonly?'切换为仅监看':'允许操作');
 notice('设备 '+label+' 正在'+action+'…');
 try{
  const result=await deviceRequest('/api/devices/access',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:device.udid,...changes})});
  if(changes.enabled===true){accessNotices.set(device.udid,{label});notice('设备 '+label+' 正在排队接入，等待画面连接…');}
  else{accessNotices.delete(device.udid);notice('设备 '+label+' 已完成'+action);}
  await refresh();
 }catch(error){notice('设备 '+label+' '+action+'未完成：'+error.message);}
 finally{accessRequests.delete(device.udid);render(latest,active,controlOwner);}
}
document.getElementById('device-context-connection').addEventListener('click',()=>{
 const target=deviceMenuTarget;closeDeviceMenu();if(target)return changeDeviceAccess(target.device,{enabled:target.device.enabled===false});
});
document.getElementById('device-context-readonly').addEventListener('click',()=>{
 const target=deviceMenuTarget;closeDeviceMenu();if(target)return changeDeviceAccess(target.device,{readonly:!target.device.readonly});
});
document.getElementById('device-context-edit').addEventListener('click',()=>{
 const target=deviceMenuTarget;closeDeviceMenu();if(target)editDevice(target.device,target.index);
});
document.getElementById('device-context-reconnect').addEventListener('click',async()=>{
 const target=deviceMenuTarget;closeDeviceMenu();if(!target||target.device.enabled===false||devicePreview)return;
 const device=target.device,label=deviceLabel(device,target.index).number;
 if(reconnectRequests.has(device.udid)||device.reconnecting||workspaceBusy||busy)return;
 reconnectRequests.add(device.udid);notice('设备 '+label+'：正在检查信任并恢复画面与操控连接…');
 try{
  const response=await fetch('/api/devices/reconnect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device:device.udid}),signal:AbortSignal.timeout(10000)});
  const result=await response.json();if(!response.ok)throw Error(result.error||'重新连接未完成');
  reconnectNotices.set(device.udid,{job:result.job,label});
 }catch(error){notice('设备 '+label+'：'+error.message);}
 finally{reconnectRequests.delete(device.udid);refresh();}
});
document.getElementById('device-context-reboot').addEventListener('click',async()=>{
 const target=deviceMenuTarget;closeDeviceMenu();if(!target||devicePreview)return;
 const device=target.device,label=deviceLabel(device,target.index).number;
 if(device.enabled===false||device.readonly||device.trust_pending||device.reconnecting||reconnectRequests.has(device.udid)||workspaceBusy||busy)return;
 if(!window.confirm('确定重启设备 '+label+'（'+device.name+'）吗？\n此手机的画面和操作会暂时断开，开机后请在手机输入密码解锁。'))return;
 reconnectRequests.add(device.udid);notice('设备 '+label+'：正在发送重启指令…');
 try{
  const response=await fetch('/api/devices/reboot',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({device:device.udid,confirm:device.udid}),signal:AbortSignal.timeout(10000)});
  const result=await response.json();if(!response.ok)throw Error(result.error||'重启请求未完成');
  reconnectNotices.set(device.udid,{job:result.job,label,operation:'reboot'});
 }catch(error){notice('设备 '+label+'：重启请求未确认，请检查手机状态；未自动重复发送。'+error.message);}
 finally{reconnectRequests.delete(device.udid);refresh();}
});
for(const [id,followup] of [['device-context-followup',true],['device-context-none',false]]){
 document.getElementById(id).addEventListener('click',()=>{
  const target=deviceMenuTarget;closeDeviceMenu();if(target)setDeviceFollowup(target.device,followup);
 });
}
followupControl.addEventListener('change',()=>{
 const context=contactFollowupContext();
 if(!context)return;
 const records=contactFollowups(context.device);
 if(followupControl.checked)records[context.key]={followup:true,contact:currentConversation.contact,
  phone_number:context.key.startsWith('phone:')?'+'+context.key.slice(6):null};else delete records[context.key];
 try{localStorage.setItem(contactFollowupStorageKey(context.device),JSON.stringify(records));}
 catch{notice('保存失败，请允许此页面使用本地存储后重试。');syncContactFollowup();return;}
 render(latest,active);
});
document.addEventListener('pointerdown',event=>{if(!deviceMenu.contains(event.target))closeDeviceMenu();},true);
window.addEventListener('blur',closeDeviceMenu);
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeDeviceMenu();});
document.addEventListener('scroll',closeDeviceMenu,true);
window.addEventListener('resize',closeDeviceMenu);
const readingPopups=new Map();
function positionReadingCards(){
 for(const [id,selector] of [['followup-panel','.followup-contact-list']]){
  const panel=document.getElementById(id);
  const popup=readingPopups.get(id)||panel.querySelector(selector);if(!popup)continue;
  if(!panel.open){if(readingPopups.has(id)){panel.append(popup);popup.classList.remove('reading-floating-card');readingPopups.delete(id);}continue;}
  if(!readingPopups.has(id)){popup.classList.add('reading-floating-card');document.body.append(popup);readingPopups.set(id,popup);}
  const bounds=panel.getBoundingClientRect();
  popup.style.maxWidth=Math.max(80,window.innerWidth-24)+'px';
  popup.style.width='max-content';
  const popupWidth=Math.min(popup.getBoundingClientRect().width,window.innerWidth-24);
  const top=Math.min(bounds.bottom+6,window.innerHeight-100);
  popup.style.width=popupWidth+'px';
  popup.style.left=Math.max(12,Math.min(bounds.right-popupWidth,window.innerWidth-popupWidth-12))+'px';
  popup.style.top=Math.max(12,top)+'px';
  popup.style.maxHeight=Math.max(80,window.innerHeight-top-12)+'px';
 }
}
document.getElementById('followup-panel').addEventListener('toggle',positionReadingCards);
window.addEventListener('resize',positionReadingCards);
document.addEventListener('scroll',positionReadingCards,true);
function deviceLabelKey(device){return 'iphone-device-label:'+(devicePreview?'preview:':'device:')+device.udid;}
function contactFollowupStorageKey(device){return 'iphone-contact-followups:'+(devicePreview?'preview:':'device:')+device.udid;}
function contactFollowups(device){
 try{
  const saved=JSON.parse(localStorage.getItem(contactFollowupStorageKey(device))||'{}');
  return saved&&typeof saved==='object'&&!Array.isArray(saved)?saved:{};
 }catch{return {};}
}
function isContactFollowup(value){return value===true||value?.followup===true;}
function contactFollowupCount(device){return Object.values(contactFollowups(device)).filter(isContactFollowup).length;}
const followupProfileCache=new Map();
let followupRenderRevision=0;
function normalizedProfilePhone(value){
 const raw=String(value||'').trim(),digits=raw.replace(/\D/g,'');
 if(!digits)return '';
 if(digits.length===10)return '1'+digits;
 if(digits.length===11&&digits.startsWith('1'))return digits;
 return digits;
}
function followupConversation(number){
 const digits=normalizedProfilePhone(number);
 return (typeof savedConversations!=='undefined'?savedConversations:[]).find(row=>
  normalizedProfilePhone(row.phone_number||row.contact)===digits);
}
function followupProfile(device,number){
 const conversation=followupConversation(number);if(!conversation?.id)return Promise.resolve({});
 const key=device+':'+conversation.id;
 if(!followupProfileCache.has(key))followupProfileCache.set(key,fetch('/api/contact-profile?'+new URLSearchParams({device,conversation:conversation.id}),{cache:'no-store'})
  .then(async response=>{const data=await response.json();if(!response.ok||data.error)throw Error(data.error||'资料读取失败');return data.fields||{};})
  .catch(()=>({})));
 return followupProfileCache.get(key);
}
window.addEventListener('contact-profile-saved',event=>{
 const {device,conversation}=event.detail||{};
 if(device&&conversation)followupProfileCache.delete(device+':'+conversation);
 if(device===active)renderFollowupContacts();
});
function contactFollowupContext(){
 const device=latest.find(row=>row.udid===active);
 if(!device||typeof currentConversation==='undefined'||!currentConversation)return null;
 if((devicePreview?previewLoadedDevice:workspaceDevice)!==device.udid)return null;
 const contact=String(currentConversation.phone_number||currentConversation.contact||'').trim();
 if(!contact)return null;
 const digits=contact.replace(/\D/g,'');
 const key=/^\+?[\d\s().-]+$/.test(contact)&&digits.length>=7?'phone:'+digits:'contact:'+contact;
 return {device,key};
}
function syncContactFollowup(){
 const context=contactFollowupContext();
 followupControl.disabled=!context;
 followupControl.checked=!!(context&&isContactFollowup(contactFollowups(context.device)[context.key]));
 followupControl.title=context?'标记当前联系人，同一手机的同一联系人只计一次':'先读取联系人会话';
 renderFollowupContacts();
}
function followupTextSelected(node){
 const selection=window.getSelection();
 return !!(selection&&!selection.isCollapsed&&(node.contains(selection.anchorNode)||node.contains(selection.focusNode)));
}
function bindFollowupContact(row,device,number){
 row.querySelector('.followup-open').onclick=()=>openFollowupContact(device,number);
}
function renderFollowupContacts(){
 const list=document.getElementById('followup-contact-list');
 if(followupTextSelected(list)||Array.from(list.children).some(row=>row.followupSelecting))return;
 const renderRevision=++followupRenderRevision;
 const existing=new Map(Array.from(list.querySelectorAll('.followup-contact'),row=>[row.dataset.followupKey,row]));
 const device=latest.find(row=>row.udid===active);
 const records=device?Object.entries(contactFollowups(device)).filter(([,value])=>isContactFollowup(value)):[];
 document.getElementById('followup-contact-count').textContent=String(records.length);
 if(!records.length){const hint=document.createElement('span');hint.className='muted';hint.textContent='在阅读区勾选联系人后显示在这里。';list.replaceChildren(hint);return;}
 const rows=[];
 for(const [key,value] of records){
  const number=key.startsWith('phone:')?'+'+key.slice(6):null;
  const rowKey=device.udid+':'+key;
  const button=existing.get(rowKey)||document.createElement('div');button.className='followup-contact';
  button.dataset.followupKey=rowKey;
  button.removeAttribute('role');button.removeAttribute('tabindex');button.removeAttribute('aria-disabled');
  if(!existing.has(rowKey)){
   const open=document.createElement('button');open.type='button';open.className='followup-open';open.textContent='打开';
   const label=document.createElement('span');label.className='followup-copy-text';label.textContent=number||value?.contact||key.slice(8);
   button.append(open,label);
  }
  const open=button.querySelector('.followup-open');open.disabled=workspaceBusy||!number;
  open.setAttribute('aria-label',number?'打开 '+number:'没有完整号码，无法打开');
  button.querySelector('.followup-copy-text').title='拖选文字后复制';
  bindFollowupContact(button,device.udid,number);rows.push(button);
  if(number)followupProfile(device.udid,number).then(fields=>{
   if(renderRevision!==followupRenderRevision||!button.isConnected||button.followupSelecting||followupTextSelected(button))return;
   const summary=['日期','姓名','年龄','工作','地区','婚否','爱好'].map(name=>
    String(fields[name]||'').replace(/\s+/g,' ').trim()).filter(Boolean).join(' ');
   const text=summary?number+' '+summary:number;
   const label=button.querySelector('.followup-copy-text');
   if(label.textContent!==text){label.textContent=text;positionReadingCards();}
  });
 }
 let cursor=list.firstChild;
 for(const row of rows){if(row===cursor)cursor=cursor.nextSibling;else list.insertBefore(row,cursor);}
 while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
 positionReadingCards();
}
async function openFollowupContact(device,number){
 if(workspaceBusy||busy||!number||active!==device)return;
 if(draftEl.value.trim()||generatedDraft){notice('回复草稿已保留，请先处理草稿再打开其他会话。');return;}
 if(devicePreview){
  const conversation=savedConversations.find(row=>String(row.phone_number||'').replace(/\D/g,'')===number.slice(1));
  if(conversation){currentConversationId=conversation.id;renderConversation();render(latest,active);}
  notice('预览：已选择 '+number+'；真实设备会输入此号码打开会话。');return;
 }
 const revision=workspaceRevision;
 await operation('正在手机打开 '+number+'，核验号码并读取短信…',async()=>{
  const result=await workspaceRequest('open',{phone_number:number},device);
  if(revision!==workspaceRevision||active!==device)return;
  if(result.phone_number!==number)throw Error('打开后的号码不一致，请核对手机。');
  await loadWorkspace(device,true,result.conversation_id);
  notice('手机已打开 '+number+'；'+(result.scope||'已读取会话原文'));
 });
}
async function showDeviceFollowups(device){
 if(workspaceBusy||busy)return;
 if(draftEl.value.trim()||generatedDraft){notice('回复草稿已保留，请先处理草稿再切换。');return;}
 if(active!==device)await select(device);
 if(active===device){document.getElementById('followup-panel').open=true;renderFollowupContacts();}
}
function loadPreviewContacts(device){
 if(typeof savedConversations==='undefined'||previewLoadedDevice===device?.udid)return;
 previewLoadedDevice=device?.udid||null;
 savedConversations=device?Array.from({length:3},(_,index)=>({
  id:device.udid+'-contact-'+index,contact:'预览联系人 '+(index+1),phone_number:'+15550000'+String(index+1).padStart(3,'0'),
  messages:[{side:'incoming',time:'12:00',kind:'text',text:'Hello, can we talk later?',translation_zh:'你好，我们可以晚点聊吗？'}]
 })):[];
 currentConversationId=savedConversations[0]?.id||null;
 renderConversation();
}
function deviceLabel(device,index){
 let saved=null;
 try{saved=JSON.parse(localStorage.getItem(deviceLabelKey(device))||'null');}catch{}
 return {number:typeof saved?.number==='string'&&saved.number.trim()?saved.number:device.number||String(index+1).padStart(2,'0'),
  followup:typeof saved?.followup==='boolean'?saved.followup:saved?.remark==='待跟进'||device.followup===true};
}
function setDeviceFollowup(device,followup){
 const label=deviceLabel(device,latest.indexOf(device));
 try{localStorage.setItem(deviceLabelKey(device),JSON.stringify({...label,followup}));}
 catch{notice('保存失败，请允许此页面使用本地存储后重试。');return;}
 render(latest,active);
}
function editDevice(device,index){
 const label=deviceLabel(device,index);editingDevice=device;
 document.getElementById('device-number-input').value=label.number;
 document.getElementById('device-label-error').textContent='';
 document.getElementById('device-label-dialog').showModal();
 document.getElementById('device-number-input').focus();
}
document.getElementById('device-label-cancel').addEventListener('click',()=>document.getElementById('device-label-dialog').close());
document.getElementById('device-label-form').addEventListener('submit',event=>{
 event.preventDefault();if(!editingDevice)return;
 const number=document.getElementById('device-number-input').value.trim();
 const error=document.getElementById('device-label-error');
 if(!number||number.length>16){error.textContent='编号必填，最多 16 字。';return;}
 const label=deviceLabel(editingDevice,latest.indexOf(editingDevice));
 try{localStorage.setItem(deviceLabelKey(editingDevice),JSON.stringify({...label,number}));}
 catch{error.textContent='保存失败，请允许此页面使用本地存储后重试。';return;}
 document.getElementById('device-label-dialog').close();editingDevice=null;
 render(latest,active);
});
function sendFocus(card,on,selected=card.node.classList.contains('selected')){if(card.frame) card.frame.contentWindow.postMessage({type:'device-focus',active:on,visible:true,selected,working:workspaceBusy,controlReady:card.controlReady===true},card.origin);}
function releasePreview(card){
 if(!card.frame)return;
 sendFocus(card,false);
 card.frame.onload=null;card.frame.remove();card.frame=null;
 card.cover?.remove();card.cover=null;
 card.connectionNotice?.remove();card.connectionNotice=null;
 card.inputReady=false;
 card.lastActive=undefined;card.lastVisible=undefined;card.lastWorking=undefined;
}
function render(rows,selected,controller=controlOwner){
 latest=rows;active=selected;controlOwner=controller;
 schedulePhoneLayout();
 if(globalMonitor)globalMonitor.selected=selected;
 for(const [udid,job] of accessNotices){
  const row=rows.find(device=>device.udid===udid);
  if(!row||row.enabled===false){notice('设备 '+job.label+' 接入已停止');accessNotices.delete(udid);}
  else if(row.ready){notice('设备 '+job.label+' 已完成接入，连接已就绪');accessNotices.delete(udid);}
  else notice('设备 '+job.label+' 正在接入：'+(row.error||'等待画面连接…'));
 }
 for(const [udid,job] of reconnectNotices){
  const row=rows.find(device=>device.udid===udid);
  if(!row){notice('设备 '+job.label+' 已断开，请接入后刷新设备列表');reconnectNotices.delete(udid);}
  else if(row.reconnect_id===job.job&&!row.reconnecting){
   notice('设备 '+job.label+'：'+(row.reconnect_state==='ready'?(job.operation==='reboot'?'手机已重启，画面与操控已恢复':'系统会话与连接已重建')+'（'+(row.reconnect_elapsed||0)+'秒）':row.reconnect_error||'连接恢复未完成，请检查手机状态'));
   reconnectNotices.delete(udid);
  }else if(row.reconnect_id===job.job&&row.reconnecting){
   const stages={stopping:'停止旧连接',rebooting:'发送手机重启指令',waiting_boot:'等待手机开机，开机后请在手机输入密码解锁',trusting:'检查并修复信任（若手机弹窗，请确认）',resetting:'清理手机端远程会话',starting:'建立新连接（重启后请先解锁手机）',checking:'检查操控通道'};
   notice('设备 '+job.label+'：正在'+(stages[row.reconnect_stage]||'重新连接')+'，已用时 '+(row.reconnect_elapsed||0)+' 秒…');
  }
 }
 syncDeviceRefreshControls();
 const connected=new Set(rows.map(device=>device.udid));
 // Keep ready viewers connected so a newly selected device already has a
 // decoded frame. Non-selected viewers throttle canvas drawing in viewer.js.
 for(const [udid,card] of cards){
  if(!rows.some(d=>d.udid===udid&&d.ready))releasePreview(card);
  if(!connected.has(udid)){card.node.remove();cards.delete(udid);}
 }
 syncDeveloperModeButton();
 if(screenshotDialog.open&&(!rows.some(d=>d.udid===selected&&d.ready)||screenshotDialog.dataset.device!==selected)){
  screenshotDialog.close();clearPhoneScreenshot();
 }
 controlPaused=false;
 syncScreenshotActions();
 if(phoneHomeButton)phoneHomeButton.disabled=!(controlOwner===selected&&rows.some(row=>row.udid===selected&&row.ready))||busy||workspaceBusy||controlPaused||devicePreview;
 const selectedDevice=rows.find(device=>device.udid===selected);
 if(devicePreview)loadPreviewContacts(selectedDevice);else{loadWorkspace(selected);syncWorkspaceControls();}
 syncContactFollowup();
 document.getElementById('device-count').textContent=rows.length+' 台';
 const deviceList=document.getElementById('device-list');deviceList.replaceChildren();
 const ordered=rows.map((device,index)=>({device,index,label:deviceLabel(device,index),followupCount:contactFollowupCount(device)}));
 ordered.sort((a,b)=>{
  const available=Number(b.device.ready===true)-Number(a.device.ready===true);
  if(available)return available;
  const manualOff=Number(a.device.enabled===false)-Number(b.device.enabled===false);
  if(manualOff)return manualOff;
  const numberOrder=String(a.label.number).localeCompare(String(b.label.number),undefined,{numeric:true})||a.index-b.index;
  return sortControl.value==='unread'?
   ((b.device.notifications?.card_count??b.device.notifications?.items?.length??0)-(a.device.notifications?.card_count??a.device.notifications?.items?.length??0)||a.index-b.index):
   sortControl.value==='followup'?(b.followupCount-a.followupCount||a.index-b.index):numberOrder;
 });
 for(const {device:d,index,label,followupCount} of ordered){
  const entry=document.createElement('button');entry.type='button';entry.className='device-entry'+(selected===d.udid?' current':'');entry.disabled=busy||workspaceBusy||refreshingDevices;entry.setAttribute('aria-pressed',String(selected===d.udid));
  entry.dataset.udid=d.udid;
  const number=label.number;
  const name=document.createElement('strong');name.textContent='设备 '+number;
  const remark=document.createElement('span');remark.className='device-remark'+(followupCount||label.followup?' followup':'');remark.textContent=followupCount||label.followup?'待跟进 '+followupCount:'无';
  remark.title='阅读区已勾选 '+followupCount+' 位联系人';
  remark.addEventListener('click',event=>{event.stopPropagation();showDeviceFollowups(d.udid);});
  const detail=document.createElement('span');detail.className='device-state';
  const phone=document.createElement('span');phone.className='device-phone';phone.setAttribute('aria-hidden','true');
  const notification=d.notifications;
  const count=notification?.card_count??notification?.items?.length??0;
  if(count){
   const badge=document.createElement('span');badge.className='notification-badge';badge.textContent=String(count);
   phone.append(badge);
  }
  const setupError=String(d.error||'');
  const setupState=d.enabled===false?'已手动断开':setupError.includes('开发者模式未开启')?'开发者模式关闭':setupError.includes('信任')?'需解锁并信任':setupError.includes('镜像准备失败')?'投屏准备失败':'正在准备投屏';
  detail.textContent=devicePreview?'':!d.ready?setupState:d.readonly?'仅监看':notification?.manual_control?'当前控制':notification?.protected?'草稿保护':
   notification?.state==='scanning'?'读取横幅':notification?.state==='paused'?'检查暂停':
   notification?.last_checked?(count?'有新消息提示':'暂未发现横幅'):'待检查';
  entry.title='设备 '+number+' · '+remark.textContent+' · '+d.name+' · '+d.udid.slice(-8)+' · '+detail.textContent+' · '+count+' 条已发现的短信横幅提示（非完整未读数）'+
   (d.error?' · '+d.error:notification?.error?' · '+notification.error:notification?.last_checked?' · 最近检查：'+new Date(notification.last_checked).toLocaleString():'');
  entry.setAttribute('aria-label',entry.title);
  entry.append(phone,name,remark);if(detail.textContent)entry.append(detail);entry.onclick=()=>select(d.udid);
  const tile=document.createElement('div');tile.className='device-tile';
  tile.addEventListener('contextmenu',event=>showDeviceMenu(event,d,index));
  entry.setAttribute('aria-haspopup','menu');
  entry.addEventListener('keydown',event=>{
   if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){
    const bounds=entry.getBoundingClientRect();
    showDeviceMenu({preventDefault:()=>event.preventDefault(),clientX:bounds.left,clientY:bounds.bottom},d,index);
   }
  });
  tile.append(entry);deviceList.append(tile);
 }
 if(devicePreview){
  const device=rows.find(d=>d.udid===selected);
  const label=device?deviceLabel(device,rows.indexOf(device)):null;
  document.getElementById('empty').style.display='';
  for(const id of ['capture-current','refresh-messages','send-reply'])document.getElementById(id).disabled=true;
  globalMonitor?.render(ordered,cards,sortControl.value);
  return;
 }
 for(const d of rows){
  let card=cards.get(d.udid);
  if(!card){
   const node=document.createElement('article');node.dataset.udid=d.udid;
   const label=document.createElement('div');label.className='label';
   const name=document.createElement('span');name.textContent=d.name+' · '+d.udid.slice(-6);
   const button=document.createElement('button');button.className='pick';button.textContent='选择控制';button.onclick=()=>select(d.udid);
   const connectionButton=document.createElement('button');connectionButton.className='pick';
   connectionButton.onclick=()=>{const device=latest.find(row=>row.udid===d.udid);if(device)return changeDeviceAccess(device,{enabled:device.enabled===false});};
   label.append(name,button,connectionButton);node.append(label);
   const waiting=document.createElement('div');waiting.className='waiting';waiting.textContent='正在启动投屏…';node.append(waiting);
   card={node,button,connectionButton,waiting,frame:null,origin:'http://127.0.0.1:'+d.port};cards.set(d.udid,card);
  }
  if(!d.ready)card.waiting.textContent=d.error||'正在启动投屏…';
  card.controlReady=d.control_ready===true&&!d.readonly&&d.enabled!==false&&!d.sms_task_busy;
  card.connectionButton.textContent=d.enabled===false?'接入此台':'断开此台';
  card.connectionButton.disabled=busy||workspaceBusy||accessRequests.has(d.udid)||d.reconnecting||d.trust_pending;
  if(d.ready&&!card.frame){
   card.inputReady=false;
   const frame=document.createElement('iframe');frame.title=d.name+' 实时画面';frame.src=card.origin+'/?batch=1&manager='+encodeURIComponent(location.origin);frame.allow='clipboard-read; clipboard-write';
   frame.onload=()=>sendFocus(card,controlOwner===d.udid&&active===d.udid&&!controlPaused&&!busy,active===d.udid);card.frame=frame;card.waiting.remove();card.node.append(frame);
   const cover=document.createElement('button');cover.className='cover';cover.textContent='选择 '+d.name;cover.setAttribute('aria-label','选择 '+d.name+' 进行控制');cover.onclick=()=>select(d.udid);card.cover=cover;card.node.append(cover);
   const connectionNotice=document.createElement('div');connectionNotice.className='input-connection-status';connectionNotice.setAttribute('role','status');connectionNotice.textContent='控制连接检查中…';card.connectionNotice=connectionNotice;card.node.append(connectionNotice);
  }
  if(!card.frame&&card.waiting.parentElement!==card.node)card.node.append(card.waiting);
  const on=selected===d.udid;card.node.classList.toggle('selected',on);card.button.textContent=d.readonly?'仅监看':on&&controlOwner===d.udid?'正在控制':'选择控制';card.button.disabled=!d.ready||d.readonly||busy;
  const target=document.getElementById('selected');if(card.node.parentElement!==target)target.append(card.node);
  card.node.hidden=!on;
  const foreground=on;
  const controllable=foreground&&controlOwner===d.udid&&!d.readonly&&d.enabled!==false&&!controlPaused&&!busy;
  if(card.lastActive!==controllable||card.lastVisible!==foreground||card.lastWorking!==workspaceBusy||card.lastControlReady!==card.controlReady){sendFocus(card,controllable,foreground);card.lastActive=controllable;card.lastVisible=foreground;card.lastWorking=workspaceBusy;card.lastControlReady=card.controlReady;}
 }
 const empty=document.getElementById('empty');if(empty)empty.style.display=selected?'none':'';
 const owner=rows.find(d=>d.udid===selected);
 const ownerLabel=owner?deviceLabel(owner,rows.indexOf(owner)):null;
 globalMonitor?.render(ordered,cards,sortControl.value);
}
async function select(udid){
 if(busy||workspaceBusy||refreshingDevices||phonePastePending)return;
 window.ForegroundSync?.activity('select');
 globalMonitor?.openWorkbench();
 if(devicePreview){previewSelection=udid;render(previewDevices,previewSelection);return;}
  if(busy||workspaceBusy||refreshingDevices)return;selectionRevision++;busy=true;active=udid;controlOwner=null;for(const card of cards.values()){sendFocus(card,false);card.lastActive=false;}render(latest,active);
 try{const j=await deviceRequest('/api/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({udid})});active=j.selected??j.active;controlOwner=j.active;const card=cards.get(udid);if(card)card.controlReady=j.control_ready===true;}
 catch(e){active=null;controlOwner=null;notice(e.message);}
 finally{busy=false;render(latest,active);refresh();}
}
const cpuUsage=document.getElementById('cpu-usage');let cpuUsageExpiry=null;
function showCpuUsage(value){
 clearTimeout(cpuUsageExpiry);cpuUsageExpiry=null;
 if(!cpuUsage)return;
 const valid=typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100;
 const percent=valid?Math.round(value):null;
 document.getElementById('cpu-percent').textContent=valid?percent+'%':'--%';
 document.getElementById('cpu-bar-fill').style.width=(percent??0)+'%';
 cpuUsage.setAttribute('aria-label',valid?'CPU 使用率 '+percent+'%':'CPU 使用率暂不可用');
 cpuUsage.dataset.level=!valid?'unknown':percent>=90?'critical':percent>=80?'high':'normal';
 cpuUsage.title=valid?'整台电脑的 CPU 使用率；占用较高时，可断开暂不使用的手机。':'暂时无法获取整台电脑的 CPU 使用率';
 if(valid)cpuUsageExpiry=setTimeout(()=>showCpuUsage(null),5000);
}
window.addEventListener('pagehide',()=>clearTimeout(cpuUsageExpiry));
let cpuRefreshing=false;
async function refreshCpuUsage(){
 if(devicePreview||cpuRefreshing)return;
 cpuRefreshing=true;
 try{const j=await deviceRequest('/api/cpu',{cache:'no-store'},2500);showCpuUsage(j.cpu_percent);}
 catch{showCpuUsage(null);}
 finally{cpuRefreshing=false;}
}
async function refresh(){if(devicePreview){showCpuUsage(null);render(previewDevices,previewSelection);return;}const revision=selectionRevision;try{const j=await deviceRequest('/api/state',{cache:'no-store'},8000);if(!busy&&revision===selectionRevision)render(j.devices,j.selected??j.active,j.active);}catch(e){notice('管理页面连接中断');}}
refresh();refreshCpuUsage();if(!devicePreview){setInterval(refresh,2000);setInterval(refreshCpuUsage,3000);}

// New-message tasks: browser storage restores unfinished form input; submission
// creates a durable backend task, which sends now or at the selected local time.
(() => {
 const dialog=document.getElementById('new-sms-dialog'),form=document.getElementById('new-sms-form');
 const get=id=>document.getElementById('new-sms-'+id);
 const storageKey='iphone-new-sms-task-draft:v1';
 const lastTaskKey='iphone-new-sms-last-task:v1';
 let imported=null,devices={},fileRevision=0,inflight=false,lastTaskId=null,pollTimer=0,saveTimer=0;
 const status=(message,error=false)=>{get('status').textContent=message;get('status').dataset.error=String(error);};
 const taskStatus=(message,error=false)=>{get('task-status').textContent=message;get('task-status').dataset.error=String(error);};
 function normalize(value){
  const clean=value.trim().replace(/[\s()\-]/g,'');
  if(/^\+\d{7,15}$/.test(clean))return clean;
  if(/^\d{10}$/.test(clean))return '+1'+clean;
  if(/^1\d{10}$/.test(clean))return '+'+clean;
  return null;
 }
 function parseNumbers(text){
  const seen=new Set(),numbers=[],invalid=[];let duplicates=0;
  text.replace(/^\uFEFF/,'').split(/\r?\n/).forEach((line,index)=>{
   if(!line.trim())return;
   const number=normalize(line);
   if(!number){invalid.push(index+1);return;}
   if(seen.has(number)){duplicates++;return;}
   seen.add(number);numbers.push(number);
  });
  return {numbers,duplicates,invalid};
 }
 const texts=()=>get('texts').value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
 function showImport(){
  const preview=get('number-preview');preview.replaceChildren();preview.hidden=!imported?.numbers?.length;
  if(!imported){get('file-info').textContent='尚未导入文件';return;}
  get('file-info').textContent=imported.name+' · '+imported.numbers.length+' 个有效号码'+
   (imported.duplicates?' · 去重 '+imported.duplicates+' 个':'')+
   (imported.invalid.length?' · 无效行 '+imported.invalid.slice(0,8).join('、')+(imported.invalid.length>8?'…':''):'');
  preview.textContent=imported.numbers.slice(0,6).join('　')+(imported.numbers.length>6?'　…':'');
 }
 function captureDevices(){
  for(const row of get('devices').querySelectorAll('[data-device]')){
   devices[row.dataset.device]={selected:row.querySelector('input[type=checkbox]').checked,
    min:Number(row.querySelector('[data-min]').value),max:Number(row.querySelector('[data-max]').value)};
  }
 }
 function saveLocalDraft(){
  captureDevices();
  const currentDevices=Object.fromEntries(Object.entries(devices).filter(([id])=>latest.some(device=>device.udid===id)));
  const draft={version:1,name:get('name').value,imported,texts:texts(),devices:currentDevices,
   concurrency:Number(get('concurrency').value),startMode:form.querySelector('[name=new-sms-start-mode]:checked').value,
   startLocal:get('start-at').value,savedAt:new Date().toISOString(),status:'draft'};
  try{localStorage.setItem(storageKey,JSON.stringify(draft));}catch{}
 }
 function scheduleLocalDraftSave(){clearTimeout(saveTimer);saveTimer=setTimeout(saveLocalDraft,250);}
 function renderDevices(){
  const list=get('devices');list.replaceChildren();
  if(!latest.length){const hint=document.createElement('p');hint.className='new-sms-hint muted';hint.textContent='尚未发现设备，连接手机后重新打开此弹窗。';list.append(hint);return;}
  latest.map((device,index)=>({device,index,label:deviceLabel(device,index)}))
   .sort((a,b)=>String(a.label.number).localeCompare(String(b.label.number),undefined,{numeric:true}))
   .forEach(({device,label})=>{
    const settings=devices[device.udid]||{selected:device.udid===active&&device.ready===true,min:15,max:25};
    const blocked=device.readonly||device.enabled===false;
    const row=document.createElement('div');row.className='new-sms-device-row';row.dataset.device=device.udid;row.dataset.ready=String(device.ready===true);
    const title=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!!settings.selected&&!blocked;check.disabled=!!blocked;
    const name=document.createElement('span');name.textContent='设备 '+label.number;
    title.append(check,name);
    if(blocked||!device.ready){const note=document.createElement('small');note.textContent=blocked?'不可用':'待连接';title.append(note);}
    row.append(title);
    for(const field of ['min','max']){
     const input=document.createElement('input');input.type='number';input.min='1';input.max='86400';input.value=String(Number.isFinite(settings[field])?settings[field]:15);
     input.setAttribute('data-'+field,'');input.setAttribute('aria-label','设备 '+label.number+(field==='min'?' 最小间隔秒数':' 最大间隔秒数'));input.disabled=!!blocked;row.append(input);
    }
    list.append(row);
   });
 }
 const updateTiming=()=>{const scheduled=form.querySelector('[name=new-sms-start-mode]:checked').value==='scheduled';get('start-at').disabled=!scheduled;get('submit').textContent=scheduled?'保存定时发送':'立即发送';};
 const terminal=new Set(['completed','completed_with_errors','failed','uncertain','cancelled']);
 function taskLabel(task){
  const labels={scheduled:'已定时',queued:'等待开始',waiting_for_device:'等待设备恢复',running:'正在执行',completed:'全部发送完成',completed_with_errors:'部分完成',failed:'发送失败',uncertain:'发送结果待核对',cancelled:'已取消'};
  const sent=task.counts?.sent_verified||0,total=task.total||0;
  return `${task.name||'短信任务'}：${labels[task.status]||task.status} · 已确认发送 ${sent}/${total}`+(task.error?' · '+task.error:'');
 }
 async function refreshTask(id){
  if(!id||!dialog.open)return;
  try{
   const task=await deviceRequest('/api/sms-tasks?id='+encodeURIComponent(id),{cache:'no-store'},8000);
   if(id!==lastTaskId)return;
   taskStatus(taskLabel(task),['failed','uncertain','completed_with_errors'].includes(task.status));
   get('cancel').hidden=terminal.has(task.status);get('cancel').dataset.taskId=id;
   if(terminal.has(task.status)){clearInterval(pollTimer);pollTimer=0;}
  }catch(error){taskStatus('任务状态暂时无法读取：'+error.message,true);}
 }
 function watchTask(id){clearInterval(pollTimer);if(!id)return;void refreshTask(id);pollTimer=setInterval(()=>void refreshTask(id),2000);}
 function open(){
  let draft=null;try{draft=JSON.parse(localStorage.getItem(storageKey)||'null');}catch{}
  imported=null;devices={};get('texts').value='';get('min').value='15';get('max').value='25';get('concurrency').value='2';
  const now=new Date(),tomorrow=new Date(now.getFullYear(),now.getMonth(),now.getDate()+1,6),z=n=>String(n).padStart(2,'0');
  get('name').value='短信任务 '+now.getFullYear()+'-'+z(now.getMonth()+1)+'-'+z(now.getDate());
  get('start-at').value=tomorrow.getFullYear()+'-'+z(tomorrow.getMonth()+1)+'-'+z(tomorrow.getDate())+'T06:00';
  form.querySelector('[name=new-sms-start-mode][value=immediate]').checked=true;
  if(draft?.version===1){
   if(draft.imported&&Array.isArray(draft.imported.numbers)&&Array.isArray(draft.imported.invalid))imported=draft.imported;
   if(draft.devices&&typeof draft.devices==='object')devices=draft.devices;
   get('name').value=draft.name||get('name').value;
   get('texts').value=Array.isArray(draft.texts)?draft.texts.join('\n'):'';
   get('concurrency').value=String(draft.concurrency||2);
   if(draft.startMode==='scheduled')form.querySelector('[name=new-sms-start-mode][value=scheduled]').checked=true;
   if(draft.startLocal)get('start-at').value=draft.startLocal;
  }
  fileRevision++;get('file').value='';showImport();renderDevices();updateTiming();
  get('text-count').textContent=texts().length+' 条';
  get('timezone').textContent='本地时区：'+Intl.DateTimeFormat().resolvedOptions().timeZone;
  status(draft?'已恢复上次未提交的配置。':'导入号码、填写正文并选择设备。');
  try{lastTaskId=localStorage.getItem(lastTaskKey)||null;}catch{lastTaskId=null;}
  taskStatus('');get('cancel').hidden=true;get('submit').disabled=false;inflight=false;
  dialog.showModal();
  watchTask(lastTaskId);
 }
 document.getElementById('new-sms-task').addEventListener('click',open);
 get('close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>{fileRevision++;clearInterval(pollTimer);pollTimer=0;clearTimeout(saveTimer);});
 form.addEventListener('input',scheduleLocalDraftSave);
 form.addEventListener('change',scheduleLocalDraftSave);
 form.querySelectorAll('[name=new-sms-start-mode]').forEach(input=>input.addEventListener('change',updateTiming));
 form.querySelector('.new-sms-file-button').addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();get('file').click();}});
 get('texts').addEventListener('input',()=>{get('text-count').textContent=texts().length+' 条';});
 get('select-all').addEventListener('click',()=>{for(const row of get('devices').querySelectorAll('[data-device]')){const input=row.querySelector('input[type=checkbox]');input.checked=row.dataset.ready==='true'&&!input.disabled;}scheduleLocalDraftSave();});
 get('select-none').addEventListener('click',()=>{get('devices').querySelectorAll('input[type=checkbox]').forEach(input=>{input.checked=false;});scheduleLocalDraftSave();});
 get('apply-interval').addEventListener('click',()=>{
  const min=Number(get('min').value),max=Number(get('max').value);
  if(!Number.isInteger(min)||!Number.isInteger(max)||min<1||max<min||max>86400){status('请输入有效间隔：1–86400 秒，最大值不能小于最小值。',true);return;}
  for(const row of get('devices').querySelectorAll('[data-device]'))if(row.querySelector('input[type=checkbox]').checked){row.querySelector('[data-min]').value=String(min);row.querySelector('[data-max]').value=String(max);}
  status('已应用到勾选设备，各台仍可单独修改。');
  scheduleLocalDraftSave();
 });
 get('file').addEventListener('change',async()=>{
  const file=get('file').files[0],revision=++fileRevision;if(!file)return;
  if(!/\.txt$/i.test(file.name)||file.size>2*1024*1024){status('请选择不超过 2 MB 的 TXT 文件。',true);return;}
  try{
   const bytes=new Uint8Array(await file.arrayBuffer());let text;
   if(bytes[0]===255&&bytes[1]===254)text=new TextDecoder('utf-16le').decode(bytes);
   else if(bytes[0]===254&&bytes[1]===255)text=new TextDecoder('utf-16be').decode(bytes);
   else{try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{text=new TextDecoder('gb18030',{fatal:true}).decode(bytes);}}
   const parsed=parseNumbers(text);
   if(revision!==fileRevision||!dialog.open)return;
   imported={name:file.name,importedAt:new Date().toISOString(),...parsed};showImport();
   status(parsed.numbers.length?'号码已导入，原 TXT 不变。':'未找到有效号码，请检查文件内容。',!parsed.numbers.length);scheduleLocalDraftSave();
  }catch{if(revision===fileRevision)status('文件读取失败，请检查文件编码或重新选择。',true);}
 });
 get('cancel').addEventListener('click',async()=>{
  const id=get('cancel').dataset.taskId;if(!id)return;
  get('cancel').disabled=true;
  try{await deviceRequest('/api/sms-tasks/'+encodeURIComponent(id)+'/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'},8000);taskStatus('已请求取消；正在发送的单条短信会先完成，不会自动重发。');void refreshTask(id);}
  catch(error){taskStatus('取消失败：'+error.message,true);}
  finally{get('cancel').disabled=false;}
 });
 form.addEventListener('submit',async event=>{
  event.preventDefault();captureDevices();
  if(inflight)return;
  if(devicePreview){status('预览模式不能创建或发送短信任务。',true);return;}
  const available=new Set(latest.filter(device=>!device.readonly&&device.enabled!==false).map(device=>device.udid));
  const ready=new Set(latest.filter(device=>device.ready&&!device.readonly&&device.enabled!==false).map(device=>device.udid));
  const selected=Object.entries(devices).filter(([id,value])=>value.selected&&available.has(id));
  if(!imported?.numbers.length){status('请先导入有效号码 TXT。',true);return;}
  if(imported.invalid.length){status('TXT 存在无效行，请修正后重新导入；任务未创建。',true);return;}
  const library=texts();if(!library.length||library.some(text=>text.length>6000)){status('文本库至少需要一条正文，每条不超过 6000 字。',true);return;}
  if(!selected.length){status('请至少勾选一台参与设备。',true);return;}
  if(selected.some(([,value])=>!Number.isInteger(value.min)||!Number.isInteger(value.max)||value.min<1||value.max<value.min||value.max>86400)){status('请检查勾选设备的间隔：1–86400 秒，最大值不能小于最小值。',true);return;}
  const concurrency=Number(get('concurrency').value);if(!Number.isInteger(concurrency)||concurrency<1||concurrency>20||concurrency>selected.length){status('同时操作设备数须为 1–20，且不能超过所选设备数。',true);return;}
  const startMode=form.querySelector('[name=new-sms-start-mode]:checked').value,startLocal=get('start-at').value;
  if(startMode==='scheduled'&&(!startLocal||!Number.isFinite(new Date(startLocal).getTime())||new Date(startLocal).getTime()<=Date.now())){status('请选择未来的定时开始日期和时间。',true);return;}
  if(startMode==='immediate'&&selected.some(([id])=>!ready.has(id))){status('立即发送所选设备必须已就绪；设备恢复画面后重试，或改为定时发送。',true);return;}
  const taskDevices=Object.fromEntries(selected.map(([id,value])=>[id,{min:value.min,max:value.max}]));
  const payload={name:get('name').value.trim(),numbers:imported.numbers,texts:library,devices:taskDevices,concurrency,startMode,
   startAt:startMode==='scheduled'?new Date(startLocal).toISOString():null,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone};
  inflight=true;get('submit').disabled=true;get('submit').setAttribute('aria-busy','true');status(startMode==='scheduled'?'正在保存定时发送任务…':'正在创建立即发送任务…');
  try{
   const task=await deviceRequest('/api/sms-tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)},20000);
   lastTaskId=task.id;try{localStorage.setItem(lastTaskKey,lastTaskId);}catch{}
   status(startMode==='scheduled'?'定时发送任务已保存；到时会自动执行。':'立即发送任务已创建，后台开始执行。');
   taskStatus(taskLabel(task));get('cancel').dataset.taskId=task.id;get('cancel').hidden=false;
   watchTask(task.id);
  }catch(error){status('任务未创建：'+error.message,true);}
  finally{inflight=false;get('submit').disabled=false;get('submit').removeAttribute('aria-busy');}
 });
})();









