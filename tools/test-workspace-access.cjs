const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const bridge = await import(pathToFileURL(path.join(__dirname,'bridge-client/workspace-access.ts')).href);
  const key=Buffer.from('01'.repeat(32),'hex');
  const url='http://127.0.0.1:8070/api/state?device=13';
  const sign=bridge.signWorkspaceRequest('GET',url,key,'1700000000','a'.repeat(32));
  const expected=require('node:crypto').createHmac('sha256',key).update('v1\nGET\n8070\n/api/state?device=13\n1700000000\n'+'a'.repeat(32)).digest('hex');
  assert.equal(sign,`v1:1700000000:${'a'.repeat(32)}:${expected}`);
  const headers={'User-Agent':'same-as-Chrome','x-pikachu-workspace-auth':'forged'};
  const authorized=bridge.workspaceAccessHeaders('apple','GET',url,headers,()=>key);
  assert.ok(authorized[bridge.workspaceAuthHeader]);
  assert.equal(authorized['User-Agent'],headers['User-Agent']);
  assert.equal(bridge.workspaceAccessHeaders('whatsapp','GET',url,headers,()=>key)[bridge.workspaceAuthHeader],undefined);
  for(const value of ['https://example.com/','http://127.0.0.1.evil.test:8070/','http://user@127.0.0.1:8070/','http://localhost:8070/','http://127.0.0.1:5173/']) {
    assert.equal(bridge.isWorkspaceTarget(value),false,value);
    assert.equal(bridge.workspaceAccessHeaders('apple','GET',value,headers,()=>key)[bridge.workspaceAuthHeader],undefined);
  }
  assert.ok(bridge.isWorkspaceTarget('http://127.0.0.1:8092/stream.bin'));
  assert.throws(()=>bridge.workspaceAccessHeaders('apple','GET',url,headers,()=>{throw Error('no credential');}));
  console.log('Translator request signing and scope checks passed');
  console.log(JSON.stringify({vector:sign}));
})().catch(error=>{console.error(error);process.exitCode=1;});
