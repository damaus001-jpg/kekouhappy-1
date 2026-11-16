const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'web/workspace.js'), 'utf8');
const code = source.slice(source.indexOf('function pasteReplyToPhone()'), source.indexOf("draftEl.addEventListener('keydown'"));
function setup() {
    let click, receive;
    const messages = [], notices = [];
    const frame = {contentWindow: {postMessage: (data, origin) => messages.push({data, origin})}};
    const ctx = {
        workspaceBusy: false, phonePastePending: null, workspaceDevice: 'phone-a', workspaceRevision: 2,
        sendBlocked: false, draftEl: {value: '  中文\nHello 🙂  '},
        cards: new Map([['phone-a', {frame, origin: 'http://127.0.0.1:8080'}]]),
        document: {getElementById: () => ({addEventListener: (name, fn) => {click = fn;}})},
        window: {addEventListener: (name, fn) => {receive = fn;}},
        crypto: {randomUUID: () => 'request-one'}, setTimeout: () => 1, clearTimeout() {},
        replyControlAvailable: () => true, syncWorkspaceControls() {}, notice: text => notices.push(text),
    };
    vm.createContext(ctx); vm.runInContext(code, ctx);
    return {ctx, messages, notices, frame, click: () => click(), receive: e => receive(e)};
}
const test = setup(); test.click(); test.click();
assert.equal(test.messages.length, 1);
assert.equal(test.messages[0].data.text, test.ctx.draftEl.value);
assert.equal(test.messages[0].data.type, 'paste-composer');
assert.equal(test.messages[0].origin, 'http://127.0.0.1:8080');
const event = {source: test.frame.contentWindow, origin: test.messages[0].origin,
    data: {type: 'paste-composer-result', id: 'request-one', ok: true}};
test.receive({...event, source: {}}); assert(test.ctx.phonePastePending);
test.receive({...event, origin: 'https://example.com'}); assert(test.ctx.phonePastePending);
test.receive(event);
assert.equal(test.ctx.phonePastePending, null);
assert.equal(test.ctx.sendBlocked, true);
assert.equal(test.ctx.draftEl.value, '  中文\nHello 🙂  ');
assert(test.notices.at(-1).includes('点击手机发送按钮'));
const switched = setup(); switched.click(); switched.ctx.workspaceDevice = 'phone-b';
switched.receive({...event, source: switched.frame.contentWindow});
assert.equal(switched.ctx.sendBlocked, false);
assert.equal(switched.ctx.phonePastePending, null);
assert(!switched.notices.at(-1).includes('点击手机发送按钮'));
console.log('Manual paste button passed: exact text, duplicate guard, source/origin checks, device switch, draft preservation; no send request');

const enter=setup();let onKey;
enter.ctx.draftEl.addEventListener=(type,callback)=>{if(type==='keydown')onKey=callback;};
enter.ctx.submitReplyInput=()=>{throw Error('Enter must never invoke the send path');};
vm.runInContext(source.slice(source.indexOf("draftEl.addEventListener('keydown'"),source.indexOf('function submitReplyInput()')),enter.ctx);
let prevented=0;
onKey({key:'Enter',isComposing:true,preventDefault(){prevented++;}});
onKey({key:'Enter',shiftKey:true,preventDefault(){prevented++;}});
assert.equal(enter.messages.length,0);assert.equal(prevented,0);
onKey({key:'Enter',preventDefault(){prevented++;}});
onKey({key:'Enter',repeat:true,preventDefault(){prevented++;}});
assert.equal(enter.messages.length,1);
assert.equal(enter.messages[0].data.type,'paste-composer');
assert.equal(enter.messages[0].data.text,enter.ctx.draftEl.value);
assert.equal(enter.ctx.draftEl.value,'  中文\nHello 🙂  ');
console.log('Composer Enter passed: shared paste path without a saved conversation, no send, repeat guard, Shift+Enter newline and IME confirmation');
