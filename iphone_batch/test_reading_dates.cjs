const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {ensureBrowser, localJson, CDP} = require('./gpt_browser.cjs');

async function run() {
 const port = await ensureBrowser(path.join(__dirname,'.device-data/reading-dates-test'), {headless:true});
 const target = await localJson(port, '/json/new?about:blank', 'PUT');
 const client = await CDP.connect(target.webSocketDebuggerUrl);
 try {
  const html = fs.readFileSync(path.join(__dirname,'web/workspace.html'),'utf8');
  const script = fs.readFileSync(path.join(__dirname,'web/workspace.js'),'utf8');
  await client.evaluate(`document.body.innerHTML=${JSON.stringify(html.match(/<body[^>]*>([\s\S]*)<\/body>/i)[1].replace(/<script[\s\S]*?<\/script>/gi,''))}; true`);
  const labels = await client.evaluate(script + `
   savedConversations=[{id:'demo',messages:[
    {date_label:'Thu, Oct 8 at 18:33',time:'18:33',text:'A'},
    {date_label:'Thu, Oct 8 at 18:33',time:'18:36',text:'B'},
    {date_label:'Today 17:26',time:'17:31',text:'C'},
    {date_label:'Friday at 9:05 PM',time:'21:09',text:'D'},
    {time:'10:00',text:'E'},
    {time:'2025-12-31T23:59:42+00:00',text:'F'}
   ]}];currentConversationId='demo';renderConversation();
   const dates=()=>Array.from(document.querySelectorAll('.message-date'),n=>n.textContent);
   const first=dates(); savedConversations[0].messages[2].date_label='Yesterday 17:26';renderConversation();
   ({first, second:dates(), count:document.getElementById('message-count').textContent,
     last:document.querySelectorAll('.message-meta')[5].textContent})
  `);
  assert.deepEqual(labels.first,['10月8日 周四 18:33','今天 17:26','周五 21:05','日期待确认','2025年12月31日']);
  assert.deepEqual(labels.second,labels.first.map(label=>label.replace('今天','昨天')));
  assert.equal(labels.count,'6 条记录');
  assert.match(labels.last,/23:59:42 UTC/);
  console.log('Chinese date separators and relative-date refresh passed in browser');
 } finally {
  await client.call('Browser.close').catch(()=>{});
  client.close();
 }
}
run().catch(error=>{console.error(error);process.exitCode=1;});
