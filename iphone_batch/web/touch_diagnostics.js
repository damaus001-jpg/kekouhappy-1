// Development-only, bounded numeric telemetry. Never sends phone input.
class TouchDiagnostics {
    constructor({enabled = false, state = () => ({}), request = (body) => fetch('/touch-diagnostics', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
        signal: AbortSignal.timeout(3000)}), setTimer = (fn, ms) => setTimeout(fn, ms) } = {}) {
        Object.assign(this, {enabled, state, request, setTimer});
        this.queue = []; this.timer = null; this.busy = false; this.dropped = 0;
    }
    record(event, fields = {}) {
        if (!this.enabled) return;
        if (this.queue.length >= 48) { this.dropped++; return; }
        const allowed = new Set(['button', 'pointer_id', 'active_pointer', 'input_ready',
            'batch_active', 'pointer_running', 'pointer_active', 'queue']);
        const numeric = Object.fromEntries(Object.entries({...this.state(), ...fields})
            .filter(([key, value]) => allowed.has(key) && (typeof value === 'boolean' || Number.isFinite(value))));
        this.queue.push({event, ...numeric, client_at_ms: Date.now(), client_monotonic_ms: performance.now(), dropped: this.dropped});
        if (this.timer === null && !this.busy) this.timer = this.setTimer(() => {
            this.timer = null; this.flush();
        }, 500);
    }
    async flush() {
        if (!this.enabled || this.busy || !this.queue.length) return;
        this.busy = true;
        const events = this.queue.splice(0, 48);
        try {
            const response = await this.request({action: 'browser', events});
            if (response?.ok === false) this.dropped += events.length;
        } catch (_) { this.dropped += events.length; }
        finally {
            this.busy = false;
            if (this.queue.length && this.timer === null) this.timer = this.setTimer(() => {
                this.timer = null; this.flush();
            }, 500);
        }
    }
}
if (typeof module !== 'undefined') module.exports = TouchDiagnostics;
