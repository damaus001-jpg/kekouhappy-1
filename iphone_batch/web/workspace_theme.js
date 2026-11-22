/* Shared with Pikachu's Apple webview; display preferences only. */
(() => {
 'use strict';
 const storageKey='pikachu-workspace-theme-v1';
 const colors=Object.freeze({blackGold:null,pink:'#FF70B6',murongPurple:'#B48EAD',clearWaterBlue:'#4AADE8'});
 const root=document.documentElement;
 const properties=new Set();
 let current='blackGold';
 const valid=theme=>typeof theme==='string'&&Object.prototype.hasOwnProperty.call(colors,theme);
 const mix=(hex,ratio)=>{
  const base=[23,25,24];
  return '#'+base.map((channel,i)=>Math.round(channel*(1-ratio)+parseInt(hex.slice(1+i*2,3+i*2),16)*ratio).toString(16).padStart(2,'0')).join('');
 };
 function render(theme){
  for(const name of properties)root.style.removeProperty(name);
  properties.clear();
  const accent=colors[theme];
  if(accent){
   const palette={'--workspace-accent':accent,'--workspace-accent-edge':mix(accent,.65),'--workspace-accent-surface':mix(accent,.18)};
   // Alpha variants keep the existing selection and glow opacity.
   for(const [name,value] of Object.entries({...palette}))
    for(const alpha of ['07','08','09','0a','0b','0d','10','13','14','18','24','26','30','3b','42','55','5c','66','ed'])
     palette[name+'-a'+alpha]=value+alpha;
   for(const [name,value] of Object.entries(palette)){root.style.setProperty(name,value);properties.add(name);}
  }
  root.dataset.pikachuTheme=theme;
  current=theme;
 }
 function apply(request){
  if(!request||typeof request!=='object'||Array.isArray(request)||request.version!==1||!valid(request.theme))return false;
  render(request.theme);
  try{localStorage.setItem(storageKey,request.theme);}catch{}
  return true;
 }
 let saved=null;
 try{saved=localStorage.getItem(storageKey);}catch{}
 render(valid(saved)?saved:'blackGold');
 window.pikachuWorkspaceTheme=Object.freeze({version:1,apply,get current(){return current;}});
 window.addEventListener('storage',event=>{
  if(event.key===storageKey){
   if(event.newValue===null)render('blackGold');
   else if(valid(event.newValue))render(event.newValue);
  }else if(event.key===null){
   render('blackGold');
  }
 });
})();
