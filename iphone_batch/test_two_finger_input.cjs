const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const PointerInput = require('./web/pointer_input.js');
const source = fs.readFileSync(path.join(__dirname, 'web/viewer.js'), 'utf8');
function setup() {
    const listeners = new Map(), sent = [];
    const target = name => ({addEventListener(type, fn) {
        const key = name + ':' + type;
        listeners.set(key, [...(listeners.get(key) || []), fn]);
    }});
    const context = {
        PointerInput, WheelInput: PointerInput.WheelInput, TwoFingerDrag: PointerInput.TwoFingerDrag,
        canvas: {...target('canvas'), focus() {}, setPointerCapture() {},
            getBoundingClientRect: () => ({left: 0, top: 0, right: 1000, bottom: 1000, width: 1000, height: 1000})},
        window: target('window'), document: {...target('document'), visibilityState: 'visible'},
        touchCoords: e => ({x: Math.round(e.clientX), y: Math.max(0, Math.min(1000, e.clientY))}),
        controlAvailable: () => context.ready, ready: true, batchActive: true,
        pasteRevision: 0, inputEpoch: 0, batchManaged: false,
        fetch: async (_, options) => { sent.push(JSON.parse(options.body)); return {ok: true}; },
        AbortSignal, setTimeout, clearTimeout, reportManualInputFailure(error) { throw error; },
    };
    vm.createContext(context);
    vm.runInContext(source.slice(source.indexOf('let activePointer = null;'),
        source.indexOf('// Right-click on the phone image')), context);
    function emit(where, type, extra = {}) {
        const event = {type, pointerId: 1, button: 1, buttons: 4, clientX: 300, clientY: 200,
            prevented: false, preventDefault() { this.prevented = true; }, ...extra};
        for (const fn of listeners.get(where + ':' + type) || []) fn(event);
        return event;
    }
    return {context, sent, emit, idle: () => vm.runInContext('pointerInput.idle()', context)};
}
(async () => {
    const s = setup();
    assert(s.emit('canvas', 'pointerdown').prevented);
    s.emit('window', 'pointermove', {clientY: 500});
    s.emit('window', 'pointerup', {clientY: 700, buttons: 0});
    await s.idle();
    assert.equal(s.sent[0].contacts.length, 2);
    const last = s.sent.at(-1);
    assert.equal(last.type, 'release');
    assert.deepEqual(last.contacts, [{x: 300, y: 700}, {x: 400, y: 700}]);
    assert(s.emit('canvas', 'mousedown').prevented);
    assert(s.emit('canvas', 'auxclick').prevented);
    for (const type of ['blur', 'mouseup', 'pointercancel', 'lostpointercapture']) {
        const t = setup(); t.emit('canvas', 'pointerdown');
        t.emit(type === 'lostpointercapture' ? 'canvas' : 'window', type);
        await t.idle();
        assert.equal(t.sent.at(-1).type, 'release', type);
        assert.equal(t.sent.at(-1).contacts.length, 2, type);
    }
    const edge = setup(); edge.emit('canvas', 'pointerdown', {clientX: 995});
    edge.emit('window', 'pointermove', {clientX: 1200, clientY: 400});
    edge.emit('window', 'pointerup', {clientX: 1200, clientY: 400}); await edge.idle();
    assert.deepEqual(edge.sent.at(-1).contacts, [{x: 900, y: 400}, {x: 1000, y: 400}]);
    const single = setup(); single.emit('canvas', 'pointerdown', {button: 0, buttons: 1});
    single.emit('window', 'pointermove', {button: -1, buttons: 1, clientY: 500});
    single.emit('window', 'pointerup', {button: 0, buttons: 0, clientY: 600}); await single.idle();
    assert(single.sent.every(p => !p.contacts));
    // Losing readiness during a drag must not block its eventual finger lift.
    for(const button of [0,1]){
        const lost=setup();lost.emit('canvas','pointerdown',{button,buttons:button===1?4:1});
        await lost.idle();
        lost.context.ready=false;
        lost.emit('window','mouseup',{button,buttons:0});await lost.idle();
        assert.equal(lost.sent.at(-1).type,'release');
        assert.equal(lost.sent.length,2);
    }
    const failed = [];
    const input = new PointerInput(async p => {failed.push(p); if (p.type === 'contact') throw Error('lost reply');});
    input.start({x: 10, y: 20, contacts: [{x: 10, y: 20}, {x: 30, y: 20}]});
    await input.idle();
    assert.equal(failed.at(-1).type, 'release');
    assert.equal(failed.at(-1).contacts.length, 2);
    console.log('Two-finger input passed: middle drag, endpoint, edges, blur/cancel/capture, chord release, single touch and failure cleanup');
})().catch(error => {console.error(error); process.exitCode = 1;});
