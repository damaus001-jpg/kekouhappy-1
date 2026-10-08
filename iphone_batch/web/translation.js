// Automatic visible-message translation. The video canvas always retains the original pixels.
const translateBtn=document.getElementById('translation-toggle');
const originalSwitch=document.getElementById('translation-original');
const translationStatus=document.getElementById('translation-status');
const contactInput=document.getElementById('translation-contact');
let translationOn=false, translationBusy=false, translationRevision=0;
let translationBoxes=[], lastTranslationSignature=null, stableSignature=null, stableAt=0, lastTranslateAt=0;
const translationLayer=document.createElement('canvas');
translationLayer.id='translation-layer';translationLayer.setAttribute('aria-hidden','true');
deviceFrameEl.append(translationLayer);
const translationCtx=translationLayer.getContext('2d');
const signatureCanvas=document.createElement('canvas');signatureCanvas.width=24;signatureCanvas.height=48;
const signatureCtx=signatureCanvas.getContext('2d',{willReadFrequently:true});
let lastPixels=null, lastDetectedContact='';
function translationMessage(text){translationStatus.textContent=text;}
function clearTranslation(){translationBoxes=[];translationRevision++;translationCtx.clearRect(0,0,translationLayer.width,translationLayer.height);}
function translationEligible(){return translationOn&&batchActive&&!document.hidden&&canvas.width>0&&canvas.height>0;}
function wordLines(text,font,width){
 translationCtx.font=font;const lines=[];let line='';
 for(const ch of text){if(ch==='\n'){lines.push(line);line='';continue;}if(line&&translationCtx.measureText(line+ch).width>width){lines.push(line);line=ch;}else line+=ch;}
 if(line)lines.push(line);return lines;
}
function paintTranslation(){
 if(translationLayer.width!==canvas.width||translationLayer.height!==canvas.height){translationLayer.width=canvas.width;translationLayer.height=canvas.height;}
 Object.assign(translationLayer.style,{left:canvas.offsetLeft+'px',top:canvas.offsetTop+'px',width:canvas.clientWidth+'px',height:canvas.clientHeight+'px'});
 translationCtx.clearRect(0,0,translationLayer.width,translationLayer.height);
 if(!translationOn||!batchActive||originalSwitch.checked)return;
 for(const box of translationBoxes){
  const x=box.x/1000*canvas.width,y=box.y/1000*canvas.height,w=box.w/1000*canvas.width,h=box.h/1000*canvas.height;
  const bg=box.color||[225,225,230];translationCtx.fillStyle=`rgb(${bg.join(',')})`;translationCtx.fillRect(x-2,y-2,w+4,h+4);
  let size=Math.max(10,Math.min(30,h*0.7));let lines=[];
  while(size>=9){lines=wordLines(box.translation,`${size}px "Microsoft YaHei",sans-serif`,Math.max(10,w));if(lines.length*size*1.16<=h+2)break;size--;}
  translationCtx.save();translationCtx.beginPath();translationCtx.rect(x-2,y-2,w+4,h+4);translationCtx.clip();
  translationCtx.font=`${size}px "Microsoft YaHei",sans-serif`;translationCtx.textBaseline='top';
  translationCtx.fillStyle=(bg[0]*.299+bg[1]*.587+bg[2]*.114)<150?'white':'#101015';
  lines.forEach((line,i)=>translationCtx.fillText(line,x,y+i*size*1.16));translationCtx.restore();
 }
}
async function translationRequest(body){
 const r=await fetch('/translation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok)throw Error('请求失败（HTTP '+r.status+'）');const j=await r.json();if(j.error)throw Error(j.error);return j;
}
async function translationSettings(){
 try{const r=await fetch('/translation',{cache:'no-store'});const j=await r.json();if(j.error)throw Error(j.error);
  document.getElementById('deepseek-model').value=j.model||'deepseek-flash';
  translationMessage(`${j.configured?'DeepSeek 已配置':'请先填写 DeepSeek API Key'} · 缓存 ${j.cache_entries||0} 条${j.ocr_installed?'':' · 待安装 OCR'}`);
 }catch(e){translationMessage(e.message);}
}
translateBtn.addEventListener('click',()=>{
 translationOn=!translationOn;translateBtn.textContent='自动英译中：'+(translationOn?'开启':'关闭');translateBtn.classList.toggle('active',translationOn);
 clearTranslation();lastTranslationSignature=null;stableSignature=null;
 translationMessage(translationOn?'打开短信会话，画面停稳后自动识别气泡':'自动翻译已关闭');
});
originalSwitch.addEventListener('change',()=>{paintTranslation();translationMessage(originalSwitch.checked?'正在显示英文原文':'正在显示中文译文');});
contactInput.addEventListener('input',()=>{clearTranslation();lastTranslationSignature=null;});
for(const event of ['pointerdown','wheel'])canvas.addEventListener(event,()=>{clearTranslation();stableSignature=null;stableAt=performance.now();},{passive:true});
window.addEventListener('resize',paintTranslation);
document.getElementById('deepseek-save').addEventListener('click',async()=>{
 const input=document.getElementById('deepseek-key');
 try{await translationRequest({action:'config',api_key:input.value,model:document.getElementById('deepseek-model').value});input.value='';await translationSettings();}
 catch(e){translationMessage(e.message);}
});
async function clearTranslationCache(scope){
 translationOn=false;translateBtn.textContent='自动英译中：关闭';translateBtn.classList.remove('active');clearTranslation();lastTranslationSignature=null;
 try{await translationRequest({action:'clear',scope,contact:contactInput.value.trim()||lastDetectedContact});await translationSettings();translationMessage('缓存已清理；自动翻译已暂停');}
 catch(e){translationMessage(e.message);}
}
document.getElementById('cache-clear-contact').addEventListener('click',()=>clearTranslationCache('contact'));
document.getElementById('cache-clear-all').addEventListener('click',()=>clearTranslationCache('all'));
document.getElementById('translate-panel-text').addEventListener('click',async()=>{
 try{const j=await translationRequest({action:'text',contact:contactInput.value.trim()||lastDetectedContact,texts:[clipboardTextEl.value]});document.getElementById('translation-text-result').textContent=j.translations[0];translationMessage(`文字翻译完成 · 命中缓存 ${j.cache_hits} 条`);}
 catch(e){translationMessage(e.message);}
});
setInterval(async()=>{
 paintTranslation();
 if(!translationEligible()){if(!batchActive&&translationBoxes.length)clearTranslation();return;}
 try{
  signatureCtx.drawImage(canvas,0,canvas.height*.14,canvas.width,canvas.height*.7,0,0,24,48);
  const pixels=signatureCtx.getImageData(0,0,24,48).data;let difference=0;
  if(lastPixels)for(let i=0;i<pixels.length;i+=4)difference+=Math.abs(pixels[i]-lastPixels[i])+Math.abs(pixels[i+1]-lastPixels[i+1])+Math.abs(pixels[i+2]-lastPixels[i+2]);
  const changed=!lastPixels||difference/(24*48*3)>3;
  lastPixels=new Uint8ClampedArray(pixels);
  const now=performance.now();
  if(changed){clearTranslation();stableSignature=Array.from(pixels).filter((v,i)=>i%4!==3).map(v=>v>>4).join(',');stableAt=now;return;}
  if(translationBusy||originalSwitch.checked||now-stableAt<600||now-lastTranslateAt<1800||stableSignature===lastTranslationSignature)return;
  translationBusy=true;lastTranslateAt=now;const revision=translationRevision;const signature=stableSignature;const contact=contactInput.value.trim();
  const shot=document.createElement('canvas');const scale=Math.min(1,1400/Math.max(canvas.width,canvas.height));shot.width=Math.round(canvas.width*scale);shot.height=Math.round(canvas.height*scale);shot.getContext('2d').drawImage(canvas,0,0,shot.width,shot.height);
  translationMessage('正在识别可见短信…');
  const j=await translationRequest({action:'frame',contact,image:shot.toDataURL('image/jpeg',.9)});
  if(revision!==translationRevision||!translationEligible()||contact!==contactInput.value.trim())return;
  translationBoxes=j.bubbles||[];lastTranslationSignature=signature;
  lastDetectedContact=j.contact||'';
  if(!contact&&j.contact)contactInput.placeholder='?????'+j.contact;
  document.getElementById('translation-source').textContent=translationBoxes.map(box=>box.source).join('\n\n');
  translationMessage(`可见译文 ${translationBoxes.length} 条 · 缓存命中 ${j.cache_hits||0} 条 · 新请求 ${j.api_requests||0} 次`);
  paintTranslation();
 }catch(e){translationMessage(e.message);lastTranslateAt=performance.now()+6000;}
 finally{translationBusy=false;}
},400);
translationSettings();
