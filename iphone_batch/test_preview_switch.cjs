const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'web/dashboard.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(`let devicePreview=false,busy=false,workspaceBusy=false,refreshingDevices=false,
selectionRevision=0,active='old',controlOwner='old',latest=[];
const cards=new Map([['old',{}],['new',{}]]),renders=[],focus=[];
function sendFocus(card,on){focus.push(on);}
function render(rows,selected){renders.push({selected,owner:controlOwner,busy});}
let reply;function deviceRequest(){return new Promise(resolve=>reply=resolve);}
function refresh(){}function notice(message){throw Error(message);}
${source.slice(source.indexOf('async function select(udid){'),source.indexOf('async function refresh(){'))}
globalThis.start=()=>select('new');
globalThis.finish=()=>reply({selected:'new',active:'new',control_ready:true});
globalThis.snapshot=()=>({renders,focus,active,controlOwner,busy});`,context);
(async()=>{
 const task=context.start();let state=context.snapshot();
 assert.equal(state.renders[0].selected,'new','show the warmed target before control request completes');
 assert.equal(state.controlOwner,null,'do not grant control before acknowledgement');
 assert.ok(state.focus.every(on=>on===false),'old control is disabled immediately');
 context.finish();await task;state=context.snapshot();
 assert.equal(state.controlOwner,'new');assert.equal(state.busy,false);
 console.log('Preview switches before control acknowledgement; control remains gated');
})().catch(error=>{console.error(error);process.exitCode=1;});
