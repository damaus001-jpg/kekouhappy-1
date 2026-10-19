const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'web/dashboard.js'),'utf8');
const handler=source.slice(source.indexOf('async function openFollowupContact('),source.indexOf('async function showDeviceFollowups('));
(async()=>{
 const calls=[],loads=[];
 const context={workspaceBusy:false,busy:false,active:'phone-one',devicePreview:false,workspaceRevision:4,
  draftEl:{value:''},generatedDraft:null,notice(){},
  operation:async(text,run)=>run(),
  workspaceRequest:async(action,body,device)=>{calls.push({action,body,device});return {phone_number:body.phone_number,conversation_id:'fresh-record'};},
  loadWorkspace:async(...args)=>loads.push(args)};
 vm.createContext(context);vm.runInContext(handler,context);
 await context.openFollowupContact('phone-one','+15550000001');
 assert.equal(calls.length,1);assert.equal(calls[0].action,'open');
 assert.equal(calls[0].body.phone_number,'+15550000001');assert.equal(calls[0].device,'phone-one');
 assert.deepEqual(loads,[['phone-one',true,'fresh-record']]);
 context.draftEl.value='unsent draft';
 await context.openFollowupContact('phone-one','+15550000002');assert.equal(calls.length,1);
 context.draftEl.value='';
 await context.openFollowupContact('other-phone','+15550000002');assert.equal(calls.length,1);
 context.workspaceRequest=async()=>({phone_number:'+15550000002',conversation_id:'wrong-record'});
 await assert.rejects(context.openFollowupContact('phone-one','+15550000001'));
 assert.equal(loads.length,1);
 console.log('Follow-up open passed: exact phone/device, open-only request, draft protection, wrong-device and wrong-number rejection');
})().catch(error=>{console.error(error);process.exitCode=1;});
