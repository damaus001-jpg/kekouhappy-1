const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, 'web/viewer.js'), 'utf8');
const keyboard = source.slice(source.indexOf('const CODE_TO_HID'), source.indexOf('// ----- Orientation:'));
const read = source.slice(source.indexOf('async function readHostClipboard()'), source.indexOf('// Returns true when'));
const deferred = () => {let resolve; const promise = new Promise(r => {resolve = r;}); return {promise, resolve};};
const pause = () => new Promise(resolve => setImmediate(resolve));

function setup({text = '  中文\nHello 🙂  ', image = null, host, uploadStatus = 200} = {}) {
    const listeners = {}, requests = [], feedback = [];
    const node = () => ({classList: {toggle() {}, contains() {return true;}}, addEventListener() {}, setAttribute() {}});
    const canvas = node(), document = {activeElement: canvas, getElementById: node};
    const context = {
        Blob, Uint8Array, atob, URLSearchParams, AbortSignal,
        inputEpoch: 0, batchManaged: true, enabled: true,
        pointerInput: {idle: async () => {}},
        canvas, document, navigator: {}, CTRL_HOTKEYS: {},
        location: {search: '?batch=1&manager=http%3A%2F%2F127.0.0.1%3A8070'},
        parent: {postMessage(message) {feedback.push(message);}},
        window: {addEventListener(name, handler) {listeners[name] = handler;}},
        controlAvailable() {return context.enabled;},
        postJson: async (url, body) => {requests.push({url, body});},
        clipboardResult() {}, log() {}, lastShared: null,
        fingerprint: async value => value.image ? 'image:mock' : 'text:' + value.text,
        inputMonitor: {invalidate() {context.inputEpoch++; context.enabled = false;}},
        fetch: async (url, options) => {
            requests.push({url, options});
            if (url === '/host-clipboard') {
                if (host) return host.promise;
                return {ok: true, json: async () => ({text, image_png: image})};
            }
            return {ok: uploadStatus === 200 || url === '/manual-paste', status: uploadStatus};
        },
    };
    vm.createContext(context);
    vm.runInContext(keyboard + '\n' + read, context);
    const key = (code, {up = false, repeat = false, ctrlKey = true} = {}) => {
        const event = {code, key: code === 'KeyV' ? 'v' : 'Control', ctrlKey,
            metaKey: false, altKey: false, repeat, preventDefault() {this.prevented = true;}};
        listeners[up ? 'keyup' : 'keydown'](event);
        return event;
    };
    const paste = () => {key('ControlLeft'); key('KeyV', {ctrlKey: false}); key('KeyV', {up: true, ctrlKey: false}); key('ControlLeft', {up: true, ctrlKey: false});};
    const idle = () => vm.runInContext('lastKeyPost', context);
    const chords = () => requests.filter(r => r.url === '/manual-paste').map(r => JSON.parse(r.options.body));
    return {context, requests, feedback, key, paste, idle, chords};
}

(async () => {
    const text = setup();
    text.paste(); await text.idle();
    assert.equal(JSON.parse(text.requests.find(r => r.url === '/clipboard').options.body).text, '  中文\nHello 🙂  ');
    assert.deepEqual(text.chords(), [{}]);
    assert(text.feedback.some(r => r.message.includes('手动发送')));
    // Repeating the same explicit paste must refresh the phone clipboard again.
    text.paste(); await text.idle();
    assert.equal(text.requests.filter(r => r.url === '/clipboard').length, 2);

    const supplied = setup();
    await vm.runInContext("queueHostPaste('\u6b63\u6587\\n\ud83d\ude42')", supplied.context);
    await supplied.idle();
    assert(!supplied.requests.some(r => r.url === '/host-clipboard'));
    assert(supplied.requests.findIndex(r => r.url === '/manual-composer-focus') < supplied.requests.findIndex(r => r.url === '/clipboard'));
    assert.equal(JSON.parse(supplied.requests.find(r => r.url === '/clipboard').options.body).text, '\u6b63\u6587\n\ud83d\ude42');
    assert.deepEqual(supplied.chords(), [{}]);

    const focusFailed = setup();
    const focusFetch = focusFailed.context.fetch;
    focusFailed.context.fetch = async (url, options) => url === '/manual-composer-focus' ? {ok:false,status:400} : focusFetch(url,options);
    await assert.rejects(vm.runInContext("queueHostPaste('body')", focusFailed.context));
    await focusFailed.idle();
    assert(!focusFailed.requests.some(r => r.url === '/clipboard'));
    assert.deepEqual(focusFailed.chords(), []);

    const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=';
    const image = setup({text: 'image URL', image: png});
    image.paste(); await image.idle();
    const upload = image.requests.find(r => r.url === '/clipboard/image');
    assert.equal(upload.options.body.type, 'image/png');
    assert.equal(Buffer.from(await upload.options.body.arrayBuffer()).toString('base64'), png);
    assert(!image.requests.some(r => r.url === '/clipboard'));
    assert.deepEqual(image.chords(), [{}]);

    for (const options of [{text: null}, {uploadStatus: 500}]) {
        const failed = setup(options); failed.paste(); await failed.idle();
        assert.deepEqual(failed.chords(), []);
        assert(failed.feedback.some(r => r.message.includes('粘贴未完成')));
    }
    const unavailable = setup();
    unavailable.context.fetch = async () => {throw Error('clipboard unavailable');};
    unavailable.paste(); await unavailable.idle();
    assert.deepEqual(unavailable.chords(), []);
    assert(unavailable.feedback.some(r => r.message.includes('粘贴未完成')));

    const retry = setup({uploadStatus: 500});
    retry.paste(); await retry.idle();
    retry.context.fetch = async () => ({ok: true, json: async () => ({text: 'manual retry'})});
    retry.paste(); await retry.idle();
    assert.equal(retry.feedback.filter(r => r.message.includes('手动发送')).length, 1);

    const uploadWait = deferred(), moved = setup();
    const normalFetch = moved.context.fetch;
    moved.context.fetch = async (url, options) => url === '/clipboard' ? uploadWait.promise : normalFetch(url, options);
    moved.paste(); await pause();
    moved.context.inputEpoch++;
    uploadWait.resolve({ok: true}); await moved.idle();
    assert.deepEqual(moved.chords(), []);

    const denied = setup();
    denied.context.fetch = async () => ({ok: false, status: 403});
    denied.context.navigator.clipboard = {read: async () => {throw Error('must not fall back after control denial');}};
    denied.paste(); await denied.idle();
    assert.deepEqual(denied.chords(), []);
    assert(denied.feedback.some(r => r.message.includes('控制权限')));

    const hidFailure = setup();
    const hidFetch = hidFailure.context.fetch;
    hidFailure.context.fetch = async (url, options) => {
        const response = await hidFetch(url, options);
        if (url === '/manual-paste') return {ok: false, status: 500};
        return response;
    };
    hidFailure.paste(); await hidFailure.idle();
    assert.deepEqual(hidFailure.chords(), [{}]);
    assert.equal(hidFailure.context.enabled, false);

    for (const cancel of [
        ctx => {ctx.enabled = false; ctx.inputEpoch++;},
        ctx => vm.runInContext('releaseAllKeys()', ctx),
    ]) {
        const host = deferred(), cancelled = setup({host});
        cancelled.paste(); await pause(); cancel(cancelled.context);
        host.resolve({ok: true, json: async () => ({text: 'late text'})});
        await cancelled.idle();
        assert(!cancelled.requests.some(r => r.url === '/clipboard'));
        assert.deepEqual(cancelled.chords(), []);
    }

    const host = deferred(), repeated = setup({host});
    repeated.key('KeyV'); repeated.key('KeyV', {repeat: true}); repeated.key('KeyV');
    await pause(); host.resolve({ok: true, json: async () => ({text: 'one paste'})});
    await repeated.idle();
    assert.deepEqual(repeated.chords(), [{}]);

    const local = setup(); local.context.document.activeElement = {};
    assert(!local.key('KeyV').prevented);
    await local.idle(); assert.equal(local.requests.length, 0);
    console.log('Manual paste passed: Unicode, image priority, one chord, repeated content, failure and focus/control cancellation; no Return or SMS send');
})().catch(error => {console.error(error); process.exitCode = 1;});
