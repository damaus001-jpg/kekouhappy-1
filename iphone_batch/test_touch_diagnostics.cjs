const assert = require('node:assert/strict');
const TouchDiagnostics = require('./web/touch_diagnostics.js');
(async () => {
    const sent = [], timers = [];
    const trace = new TouchDiagnostics({enabled: true,
        state: () => ({input_ready: true, active_pointer: -1, text: 'secret'}),
        request: async body => { sent.push(body); return {ok: true}; },
        setTimer: fn => { timers.push(fn); return timers.length; }});
    for (let i = 0; i < 100; i++) trace.record('pointer-down', {button: 0, clipboard: 'secret'});
    assert.equal(trace.queue.length, 48);
    assert.equal(trace.dropped, 52);
    assert.equal(timers.length, 1);
    await trace.flush();
    assert.equal(sent.length, 1);
    assert(!JSON.stringify(sent).includes('secret'));
    const disabled = new TouchDiagnostics({request: () => { throw Error('must not run'); }});
    disabled.record('pointer-down');
    await disabled.flush();
    assert.equal(disabled.queue.length, 0);
    const failing = new TouchDiagnostics({enabled: true, request: async () => { throw Error('offline'); }, setTimer: () => 1});
    failing.record('pointer-down');
    await failing.flush();
    assert.equal(failing.dropped, 1);
    assert.equal(failing.busy, false);
    console.log('Touch telemetry: bounded batching, content filtering, disabled mode, failure isolation passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
