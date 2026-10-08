const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'web/viewer.js'),'utf8');
const helper = source.slice(source.indexOf('function deviceKeyUsages('),source.indexOf('function postKeys('));
const context = {};
vm.createContext(context);
vm.runInContext(helper,context);
function translated(usages, enabled=true) { return Array.from(context.deviceKeyUsages(usages,enabled)).sort((a,b)=>a-b); }
assert.deepEqual(translated([0xE0,0x06]),[0x06,0xE3]); // Ctrl+C -> Command+C
assert.deepEqual(translated([0xE4,0x19]),[0x19,0xE3]); // right Ctrl+V
assert.deepEqual(translated([0xE0,0xE1,0x04]),[0x04,0xE1,0xE3]); // preserve Shift
assert.deepEqual(translated([0xE0],false),[0xE0]); // normal Ctrl untouched
assert.deepEqual(translated([],false),[]); // key release
console.log('Windows editing shortcut mapping passed');
