const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'web/viewer.js'), 'utf8');
const read = source.slice(source.indexOf('async function readHostClipboard()'), source.indexOf('// Returns true when'));
const write = source.slice(source.indexOf('async function writeHostClipboard(content)'), source.indexOf('async function fetchDeviceContent'));
const context = {batchActive:true, navigator:{}, showInPanel:()=>{}, clipboardResult:()=>{}, fetch:null};
vm.createContext(context);
vm.runInContext(read + '\n' + write, context);
(async () => {
    let sent;
    context.fetch = async (url, options) => {
        assert.equal(url, '/host-clipboard');
        if (options.method === 'POST') sent = JSON.parse(options.body).text;
        return {ok:true, json:async()=>({text:'\u4e2d\u6587\ntext'})};
    };
    assert.equal((await context.readHostClipboard()).text, '\u4e2d\u6587\ntext');
    assert.equal(await context.writeHostClipboard({text:'\u4e2d\u6587\ntext',image:null}),true);
    assert.equal(sent,'\u4e2d\u6587\ntext');
    context.fetch = async () => ({ok:false});
    let message;
    context.clipboardResult = value => {message=value;};
    assert.equal(await context.writeHostClipboard({text:'text',image:null}),false);
    assert.ok(message);
    console.log('Text clipboard: native read/write without browser API and failure feedback passed');
})().catch(err => {console.error(err);process.exitCode=1;});
