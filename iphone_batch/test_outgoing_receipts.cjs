const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8');
const code=source.slice(source.indexOf('const outgoingReceiptCache='),source.indexOf('const monthNumbers='));
const memory=new Map(),context={console,Date,Map,Set,JSON,
 localStorage:{getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}};
vm.createContext(context);vm.runInContext(code,context);
const run=code=>vm.runInContext(code,context);
run(`globalThis.old={side:'outgoing',text:'Same',time:'10:00',kind:'text'};
 globalThis.key=outgoingMessageKey(old);
 globalThis.receipt=(id,text='Same')=>({id,device:'D',number:'+12025550123',text,baseline:[key]});
 globalThis.rows=(list)=>readingOutgoingRows('D','+12025550123',list);
 globalThis.pending=()=>outgoingReceipts('D','+12025550123');`);
assert.equal(run(`acknowledgeOutgoing(receipt('one'))`),true);
assert.equal(run(`acknowledgeOutgoing(receipt('one'))`),false);
assert.equal(run(`rows([old]).length`),2,'old identical text cannot replace the new submission');
assert.equal(run(`rows([old])[1].local_outgoing_id`),'one');
assert.equal(run(`readingOutgoingRows('E','+12025550123',[old]).length`),1);
assert.equal(run(`readingOutgoingRows('D','+19999999999',[old]).length`),1);
run(`acknowledgeOutgoing(receipt('two'));globalThis.newOne={...old,time:'10:01',bubble_status:{delivery:'not_delivered'}};`);
assert.equal(run(`rows([old,newOne]).length`),3,'one observed occurrence consumes only one matching submission');
assert.equal(run(`pending().length`),1);
assert.equal(run(`rows([old,newOne]).length`),3,'repeat render cannot consume the second submission with the first observation');
assert.equal(run(`rows([old,newOne,{...old,time:'10:02'}]).length`),3);
assert.equal(run(`pending().length`),0);
assert.equal(run(`overlayReadingRow({side:'incoming',text:'A',time:'10:00',date_label:'Today 10:00'},
 {side:'incoming',text:'A',time:'10:00',date_label:'Yesterday 10:00'}).date_label`),'Yesterday 10:00');
assert.equal(run(`readingRowsMatch({side:'outgoing',text:'Same',time:'2026-10-15T16:11:20Z',date_label:'Thu, Oct 15 at 9:11 AM'},
 {side:'outgoing',text:'Same',time:'9:11 AM'})`),true);
assert.equal(run(`readingRowsMatch({side:'outgoing',text:'Same',time:'2026-10-15T16:11:20Z',date_label:'Thu, Oct 15 at 9:11 AM'},
 {side:'outgoing',text:'Same',time:'6:12 PM'})`),false);
assert.equal(run(`rows([old,newOne])[1].bubble_status.delivery`),'not_delivered');
run(`acknowledgeOutgoing(receipt('persist','New'));outgoingReceiptCache.clear();`);
assert.equal(run(`pending()[0].id`),'persist');
assert.equal(run(`rows([old,{...old,time:'10:05',text:'New'}]).length`),2);
assert.equal(run(`pending().length`),0);
console.log('Submission identity, persistence, repeated identical sends, incremental reconciliation and device/contact isolation passed');
