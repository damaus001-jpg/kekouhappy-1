const assert = require('node:assert/strict');
const Monitor = require('./web/input_health.js');
const ticks = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
function setup(request, eligible = () => true) {
    const timers = new Map(), states = []; let next = 0;
    const monitor = new Monitor({request, eligible, changed: state => states.push(state),
        setTimer: callback => {timers.set(++next, callback); return next;},
        clearTimer: id => timers.delete(id)});
    return {monitor, states, timers, async tick() {
        const [id, callback] = [...timers.entries()][0] || [];
        assert(callback, 'expected pending health check');timers.delete(id);callback();await ticks();
    }};
}
(async () => {
    let calls = 0;
    const a = setup(async () => {calls++; return {ok: true, state: 'ready'};});
    await ticks(); assert.equal(calls, 0, 'standby never probes');
    a.monitor.setActive(true);await ticks();assert(a.monitor.ready);
    assert.equal(calls, 1);await a.tick();assert.equal(calls, 2);
    a.monitor.setActive(false);assert.equal(a.timers.size, 0);assert(!a.monitor.ready);

    let eligible = false;
    const b = setup(async () => ({ok: true, state: 'ready'}), () => eligible);
    b.monitor.setActive(true);await ticks();assert(!b.monitor.ready);
    eligible = true;await b.tick();assert(b.monitor.ready, 'idle resumes checking');

    calls = 0;
    const c = setup(async () => {calls++; throw Error('offline');});
    c.monitor.setActive(true);await ticks();await c.tick();await c.tick();
    assert.equal(calls, 3);assert.equal(c.timers.size, 0, 'permanent failure stops automatic retries');
    await c.monitor.check(true);assert.equal(calls, 4, 'manual refresh resets retry budget');
    assert(c.states.at(-1).manual);

    let resolve;
    const d = setup(() => new Promise(r => {resolve = r;}));
    d.monitor.setActive(true);const pending = d.monitor.check(true);
    assert.equal(pending, d.monitor.pending, 'automatic and manual checks share one request');
    d.monitor.setActive(false);resolve({ok: true, state: 'ready'});await pending;
    assert(!d.monitor.ready, 'old reply cannot enable a deselected device');
    assert.equal(d.timers.size, 0);

    const e = setup(async () => ({ok: true, state: 'ready'}));
    e.monitor.setActive(true);await ticks();e.monitor.invalidate();
    assert(!e.monitor.ready, 'input error immediately blocks further gestures');
    await e.tick();assert(e.monitor.ready);
    console.log('Input monitor passed: standby idle, selected polling, task/gesture pause, bounded retries, manual fallback, single flight, stale reply and recovery');
})().catch(error => {console.error(error);process.exitCode = 1;});
