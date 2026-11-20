const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {ensureBrowser, localJson, CDP} = require('./gpt_browser.cjs');

async function run() {
 const port = await ensureBrowser(path.join(__dirname,'.device-data/reading-dates-test-'+process.pid), {headless:true});
 const target = await localJson(port, '/json/new?about:blank', 'PUT');
 const client = await CDP.connect(target.webSocketDebuggerUrl);
 try {
  const html = fs.readFileSync(path.join(__dirname,'web/workspace.html'),'utf8');
  const script = fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8');
  await client.evaluate(`document.body.innerHTML=${JSON.stringify(html.match(/<body[^>]*>([\s\S]*)<\/body>/i)[1].replace(/<script[\s\S]*?<\/script>/gi,''))}; true`);
  const labels = await client.evaluate(script + `
   savedConversations=[{id:'demo',messages:[
    {date_label:'Thu, Oct 8 at 18:33',time:'18:33',text:'A',side:'outgoing',bubble_status:{sending_method:'sms'}},
    {date_label:'Thu, Oct 8 at 18:33',time:'18:36',text:'B',side:'outgoing',bubble_status:{sending_method:'rcs',delivery:'read',read_time:'15:34'}},
    {date_label:'Today 17:26',time:'17:31',text:'C',side:'outgoing',bubble_status:{delivery:'not_delivered'}},
    {date_label:'Friday at 9:05 PM',time:'21:09',text:'D',side:'incoming',bubble_status:{delivery:'read'}},
    {time:'10:00',text:'E'},
    {time:'2025-12-31T23:59:42+00:00',text:'F'}
   ]}];currentConversationId='demo';renderConversation();
   const dates=()=>Array.from(document.querySelectorAll('.message-date'),n=>n.textContent);
   const first=dates(); savedConversations[0].messages[2].date_label='Yesterday 17:26';renderConversation();
   ({first, second:dates(), count:document.getElementById('message-count').textContent,
     last:document.querySelectorAll('.message-meta')[5].textContent,
     statuses:Array.from(document.querySelectorAll('.message-status'),n=>({text:n.textContent,
       below:n.previousElementSibling.className,failed:n.classList.contains('failed')})),
     incomingStatus:document.querySelector('.incoming .message-status')!==null,
     delivered:readingBubbleStatus({side:'outgoing',bubble_status:{delivery:'delivered'}})})
  `);
  assert.deepEqual(labels.first,['10月8日 周四 18:33','今天 17:26','周五 21:05','日期待确认','2025年12月31日']);
  assert.deepEqual(labels.second,labels.first.map(label=>label.replace('今天','昨天')));
  assert.equal(labels.count,'6 条记录');
  assert.match(labels.last,/23:59:42 UTC/);
  assert.deepEqual(labels.statuses,[
   {text:'以短信形式发送',below:'bubble',failed:false},
   {text:'以 RCS 形式发送 · 已读 15:34',below:'bubble',failed:false},
   {text:'未送达',below:'bubble',failed:true}
  ]);
  assert.equal(labels.incomingStatus,false);
  assert.equal(labels.delivered,'已送达');
  console.log('Chinese date separators and relative-date refresh passed in browser');
 } finally {
  await client.call('Browser.close').catch(()=>{});
  client.close();
 }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
