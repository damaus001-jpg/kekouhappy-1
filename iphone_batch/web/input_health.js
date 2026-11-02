// One monitor per selected viewer. Queries contain no input events.
// Input health assets are read on every viewer.js request.
class InputHealthMonitor {
    constructor({request, eligible, changed, setTimer = (callback, ms) => setTimeout(callback, ms), clearTimer = timer => clearTimeout(timer)}) {
        Object.assign(this, {request, eligible, changed, setTimer, clearTimer});
        this.active = false; this.ready = false; this.failures = 0;
        this.revision = 0; this.timer = null; this.pending = null;
    }
    schedule(ms) {
        if (this.timer !== null) this.clearTimer(this.timer);
        this.timer = null;
        if (this.active && this.failures < 3) this.timer = this.setTimer(() => {
            this.timer = null; this.check();
        }, ms);
    }
    publish(state, extra = {}) { this.changed({state, ready: this.ready, ...extra}); }
    setActive(on) {
        if (this.active === on) return;
        this.active = on; this.revision++; this.ready = false; this.failures = 0;
        if (this.timer !== null) this.clearTimer(this.timer);
        this.timer = null;
        if (on) { this.publish('checking'); this.check(); }
        else this.publish('inactive');
    }
    invalidate() {
        if (!this.active) return;
        this.ready = false; this.publish('recovering'); this.schedule(0);
    }
    check(manual = false) {
        if (!this.active) return Promise.resolve(null);
        if (manual) this.failures = 0;
        if (this.pending) return this.pending;
        if (!manual && this.failures >= 3) return Promise.resolve(null);
        if (!this.eligible()) { this.schedule(1000); return Promise.resolve({state: 'busy'}); }
        if (manual) this.ready = false;
        if (!this.ready) this.publish('checking', {manual});
        const revision = this.revision;
        this.pending = (async () => {
            try {
                const result = await this.request();
                if (!this.active || revision !== this.revision) return result;
                if (result.state === 'busy') { this.schedule(1000); return result; }
                this.ready = result.ok === true && result.state === 'ready';
                if (this.ready) {
                    this.failures = 0; this.publish('ready', {recovered: result.recovered, manual});
                    this.schedule(5000);
                } else {
                    this.failures++; this.publish('unavailable', {manual});
                    this.schedule(this.failures * 3000);
                }
                return result;
            } catch (error) {
                if (this.active && revision === this.revision) {
                    this.ready = false; this.failures++; this.publish('unavailable', {manual});
                    this.schedule(this.failures * 3000);
                }
                return {ok: false, state: 'unavailable'};
            } finally {
                this.pending = null;
                if (this.active && revision !== this.revision) this.schedule(0);
            }
        })();
        return this.pending;
    }
}
if (typeof module !== 'undefined') module.exports = InputHealthMonitor;
