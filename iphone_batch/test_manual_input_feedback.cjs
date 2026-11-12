const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'web/viewer.js'), 'utf8');
const helpers = source.slice(source.indexOf('function reportManualInputFailure('), source.indexOf('let activePointer = null;'));
const buttons = source.slice(source.indexOf('// Right-click on the phone image'), source.indexOf('// The bezel buttons are too thin'));
const swipe = source.slice(source.indexOf('async function swipe(direction)'), source.indexOf("document.querySelectorAll('button[data-swipe]')"));
const pointerDown = source.slice(source.indexOf("canvas.addEventListener('pointerdown', (e) => {"), source.indexOf('function onMove(e)'));
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };

function setup({available = true, status = 200, statuses, networkError = null, managed = true, idle, feedbackError = false} = {}) {
    const listeners = {}, logs = [], feedback = [], requests = [], order = [];
    let invalidated = 0;
    const button = name => ({dataset: {btn: name}, listeners: {},
        getAttribute() { return name; }, setPointerCapture() {},
        addEventListener(type, callback) { this.listeners[type] = callback; }});
    const regular = button('home'), bezel = button('lock');
    const context = {
        URLSearchParams, AbortSignal, batchManaged: managed,
        location: {search: '?batch=1&manager=http%3A%2F%2F127.0.0.1%3A8070'},
        parent: {postMessage(data, origin) { if (feedbackError) throw Error('invalid origin'); feedback.push({data, origin}); }},
        controlAvailable() { return available; }, log(message) { logs.push(message); },
        inputMonitor: {invalidate() { invalidated++; }},
        fetch: async (url, options) => {
            order.push('request'); requests.push({url, body: JSON.parse(options.body)});
            if (networkError) throw networkError;
            const responseStatus = statuses?.[requests.length - 1] ?? status;
            return {ok: responseStatus >= 200 && responseStatus < 300, status: responseStatus};
        },
        canvas: {addEventListener(name, callback) { listeners[name] = callback; }},
        document: {querySelectorAll(selector) { return selector.includes(':not') ? [regular] : [bezel]; }},
        window: {addEventListener() {}},
        releaseActive() { order.push('release'); },
        pointerInput: {idle() { order.push('idle'); return idle || Promise.resolve(); }},
        performance: {now: () => 100}, setTimeout: callback => { callback(); },
    };
    vm.createContext(context);
    vm.runInContext(helpers + buttons + swipe + pointerDown, context);
    return {context, listeners, logs, feedback, requests, order, regular, bezel,
        invalidated: () => invalidated, clickHome() { listeners.contextmenu({preventDefault() { order.push('prevent'); }}); }};
}

(async () => {
    const blocked = setup({available: false});
    assert.equal(await blocked.context.postJson('/button', {name: 'home', state: 'press'}), false);
    assert.equal(blocked.requests.length, 0);
    assert.equal(blocked.feedback[0].origin, 'http://127.0.0.1:8070');
    assert.equal(blocked.feedback[0].data.type, 'manual-input-result');
    assert.equal(blocked.feedback[0].data.ok, false);
    assert(blocked.feedback[0].data.message.includes('尚未就绪'));
    const blockedPointer = setup({available: false});
    blockedPointer.listeners.pointerdown({button: 0});
    assert.equal(blockedPointer.requests.length, 0, 'blocked primary clicks do not inject touch');
    assert.equal(blockedPointer.feedback.length, 1);
    assert.equal(blockedPointer.feedback[0].data.ok, false);
    assert.equal(blockedPointer.invalidated(), 1);
    blockedPointer.listeners.pointerdown({button: 2});
    assert.equal(blockedPointer.feedback.length, 1, 'secondary pointerdown leaves feedback to contextmenu');

    const failed = setup({status: 403});
    failed.clickHome(); await tick();
    assert.equal(failed.requests[0].url, '/manual-home');
    assert.equal(failed.feedback[0].data.ok, false);
    assert.equal(failed.invalidated(), 1);
    assert(!failed.logs.some(message => message.includes('请求已发送')));
    assert(failed.logs.some(message => message.includes('HTTP 403')));

    const offline = setup({networkError: Error('network unavailable')});
    assert.equal(await offline.context.postJson('/key', {usages: []}), false);
    assert.equal(offline.feedback.length, 1);
    const quiet = setup({available: false, feedbackError: true});
    assert.equal(await quiet.context.postJson('/key', {usages: []}), false, 'feedback failures do not reject old keyboard chains');
    const standalone = setup({managed: false, status: 500});
    assert.equal(await standalone.context.postJson('/button', {name: 'home', state: 'press'}), false);
    assert.equal(standalone.feedback.length, 0); assert(standalone.logs.length);

    const gate = deferred(), success = setup({idle: gate.promise});
    success.clickHome(); await tick();
    assert.deepEqual(success.order, ['prevent', 'release', 'idle']);
    assert.equal(success.requests.length, 0, 'Home waits until the previous touch is released');
    gate.resolve(); await tick();
    assert.equal(success.requests.length, 1);
    assert.equal(success.requests[0].url, '/manual-home');
    assert.equal(success.logs.length, 1);
    assert(success.logs[0].includes('请求已发送') && success.logs[0].includes('核对手机画面'));
    assert.equal(success.feedback.length, 0);
    const interrupted = setup({idle: Promise.reject(Error('touch queue unavailable'))});
    interrupted.clickHome(); await tick();
    assert.equal(interrupted.requests.length, 0);
    assert.equal(interrupted.feedback[0].data.message, 'touch queue unavailable');

    for (const status of [200, 503]) {
        const sample = setup({status});
        sample.regular.listeners.click();
        sample.bezel.listeners.pointerdown({button: 0, pointerId: 1, preventDefault() {}});
        sample.bezel.listeners.click({detail: 0});
        await tick();
        assert.equal(sample.logs.filter(message => message.includes('request sent')).length, status === 200 ? 3 : 0);
    }
    const failedSwipe = setup({status: 500});
    assert.equal(await failedSwipe.context.swipe('left'), false);
    assert.deepEqual(failedSwipe.requests.map(request => request.body.type), ['contact', 'release'], 'a failed initial contact is released once without replay');
    assert.equal(failedSwipe.requests[1].body.x, failedSwipe.requests[0].body.x);
    assert(!failedSwipe.logs.some(message => message.includes('swipe request sent')));
    const interruptedSwipe = setup({statuses: [200, 500, 200]});
    assert.equal(await interruptedSwipe.context.swipe('left'), false);
    assert.deepEqual(interruptedSwipe.requests.map(request => request.body.type), ['contact', 'contact', 'release']);
    assert.equal(interruptedSwipe.requests.at(-1).body.x, interruptedSwipe.requests[1].body.x, 'release uses the last attempted contact coordinates');
    assert(!interruptedSwipe.logs.some(message => message.includes('swipe request sent')));
    const failedRelease = setup({statuses: [...Array(11).fill(200), 500]});
    assert.equal(await failedRelease.context.swipe('left'), false);
    assert.equal(failedRelease.requests.filter(request => request.body.type === 'release').length, 1, 'failed final release is not replayed');
    const successfulSwipe = setup();
    assert.equal(await successfulSwipe.context.swipe('right'), true);
    assert.equal(successfulSwipe.requests.length, 12);
    assert.equal(successfulSwipe.requests.at(-1).body.type, 'release');
    console.log('Manual input feedback passed: failures return false and notify trusted manager, Home waits for touch release, success logs only acknowledge a sent request');
})().catch(error => { console.error(error); process.exitCode = 1; });
