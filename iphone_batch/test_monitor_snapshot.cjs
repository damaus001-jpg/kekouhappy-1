const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'web/viewer.js'),'utf8');
const start=source.indexOf('    let snapshotBusy = false, lastSnapshotAt = -Infinity;');
const end=source.indexOf("        if (event.data?.type === 'input-recover')",start);
const messages=[],parent={},manager='http://127.0.0.1:8070';let listener,clock=10000,forced=0;
const context=vm.createContext({parent,location:{search:'?manager='+encodeURIComponent(manager)},URLSearchParams,
 performance:{now:()=>clock},window:{addEventListener(type,callback){listener=callback;}},
 pendingFrame:{},lastFrame:null,cancelFrameDraw(){},drawPending(force){assert.equal(force,true);forced++;},
 canvas:{width:1170,height:2532},videoConnection:{state:'streaming'},
 document:{createElement(){return {getContext(){return {drawImage(){}};},toBlob(callback,mime,quality){assert.equal(mime,'image/jpeg');assert.equal(quality,.65);callback({type:mime});}};}}
});
parent.postMessage=(data,origin)=>messages.push({data,origin});
vm.runInContext(source.slice(start,end)+'\n    });',context);
const request={source:parent,origin:manager,data:{type:'monitor-snapshot',id:'monitor-1'}};
listener({...request,source:{}});listener({...request,origin:'https://example.com'});assert.equal(messages.length,0);
listener(request);assert.equal(messages.length,1);assert.equal(forced,1);assert.equal(messages[0].origin,manager);assert.equal(messages[0].data.id,'monitor-1');
listener(request);assert.equal(messages.length,1,'requests inside the thumbnail interval are ignored');
clock+=3000;listener({...request,data:{...request.data,id:'monitor-2'}});assert.equal(messages.length,2);
assert.equal(messages[1].data.id,'monitor-2');
console.log('Monitor snapshot passed: trusted parent/origin, newest warm frame and bounded request frequency');
