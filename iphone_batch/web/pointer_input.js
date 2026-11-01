// Keep gesture edges in order and replace unsent motion with the newest position.
class PointerInput {
    constructor(send, onError = () => {}) {
        this.send = send;
        this.onError = onError;
        this.queue = [];
        this.running = false;
        this.active = false;
        this.moved = false;
        this.waiters = [];
        this.generation = 0;
        this.sentGesture = null;
        this.sentMotionGesture = null;
        this.lastSent = null;
    }
    start(coords) {
        if (this.active) return;
        this.active = true;
        this.moved = false;
        this.gesture = ++this.generation;
        this.last = {...coords};
        this.queue.push({type: 'contact', ...coords, edge: true, gesture: this.gesture});
        this.pump();
    }
    move(coords) {
        if (!this.active || (coords.x === this.last.x && coords.y === this.last.y)) return;
        this.moved = true;
        this.last = {...coords};
        const motion = {type: 'contact', ...coords, gesture: this.gesture};
        const tail = this.queue[this.queue.length - 1];
        if (tail?.type === 'contact' && !tail.edge && tail.gesture === this.gesture) this.queue[this.queue.length - 1] = motion;
        else this.queue.push(motion);
        this.pump();
    }
    end(coords = this.last, {settle = false, immediateStop = false} = {}) {
        if (!this.active) return;
        this.active = false;
        if (immediateStop) {
            this.queue = this.queue.filter(command => command.gesture !== this.gesture);
            if (this.sentGesture !== this.gesture) return;
            // If only the initial contact reached the phone, retain one drag
            // displacement so a cold first wheel gesture cannot become a tap.
            coords = this.sentMotionGesture === this.gesture ? this.lastSent : this.last;
        } else {
            const tail = this.queue[this.queue.length - 1];
            if (tail?.type === 'contact' && !tail.edge && tail.gesture === this.gesture) this.queue.pop();
        }
        this.queue.push({type: 'release', ...coords, settle: settle && this.moved, gesture: this.gesture});
        this.pump();
    }
    async pump() {
        if (this.running) return;
        this.running = true;
        let command;
        try {
            while (this.queue.length) {
                command = this.queue.shift();
                const {edge, gesture, ...payload} = command;
                if (command.type === 'contact') {
                    this.sentGesture = gesture;
                    this.lastSent = {x: command.x, y: command.y};
                    if (!edge) this.sentMotionGesture = gesture;
                }
                await this.send(payload);
            }
        } catch (error) {
            this.queue.length = 0;
            this.active = false;
            // A lost reply may still have pressed the phone. Release once.
            if (command) {
                try { await this.send({type: 'release', x: command.x, y: command.y, settle: false}); } catch (_) {}
            }
            this.onError(error);
        } finally {
            this.running = false;
            if (this.queue.length) this.pump();
            else for (const resolve of this.waiters.splice(0)) resolve();
        }
    }
    idle() {
        if (!this.running && !this.queue.length) return Promise.resolve();
        return new Promise(resolve => this.waiters.push(resolve));
    }
}
if (typeof module !== 'undefined') module.exports = PointerInput;

class WheelInput {
    constructor(pointer, {bounds, coords, enabled = () => true,
        setTimer = (callback, delay) => setTimeout(callback, delay), clearTimer = handle => clearTimeout(handle)}) {
        this.pointer = pointer;
        this.bounds = bounds;
        this.coords = coords;
        this.enabled = enabled;
        this.setTimer = setTimer;
        this.clearTimer = clearTimer;
        this.active = false;
        this.pending = 0;
        this.timer = null;
        this.clutch = false;
    }
    handle(event) {
        if (!this.enabled() || event.ctrlKey || event.metaKey || !Number.isFinite(event.deltaY) || !event.deltaY) return false;
        const rect = this.bounds();
        if (!rect.width || !rect.height || (!this.active && this.pointer.active)) return false;
        event.preventDefault();
        const multiplier = event.deltaMode === 1 ? 18 : event.deltaMode === 2 ? rect.height * .8 : 1;
        const delta = event.deltaY * multiplier;
        if (this.timer !== null) this.clearTimer(this.timer);
        // Holding the last position stops visible movement immediately. Only
        // the finger lift waits for a quiet gap, avoiding a flick per notch.
        this.timer = this.setTimer(() => this.stop(), 120);
        if (!this.active) {
            this.pending += delta;
            if (Math.abs(this.pending) < 6) return true;
            this.active = true;
            this.position = {clientX: rect.left + rect.width * .5,
                clientY: rect.top + rect.height * (this.pending > 0 ? .75 : .25)};
            this.pointer.start(this.coords(this.position));
            this.gesture = this.pointer.gesture;
            this.clutch = false;
        } else if (!this.pointer.active || this.pointer.gesture !== this.gesture) {
            this.stop();
            return true;
        } else this.pending += delta;
        const low = rect.top + rect.height * .2, high = rect.top + rect.height * .8;
        this.position.clientY = Math.max(low, Math.min(high, this.position.clientY - this.pending));
        this.pending = 0;
        this.pointer.move(this.coords(this.position));
        if (!this.clutch && (this.position.clientY === low || this.position.clientY === high)) {
            this.clutch = true;
            const gesture = this.gesture;
            this.pointer.idle().then(() => {if (this.active && this.gesture === gesture) this.stop();});
        }
        return true;
    }
    stop() {
        if (this.timer !== null) this.clearTimer(this.timer);
        this.timer = null;
        this.pending = 0;
        if (this.active && this.pointer.gesture === this.gesture) {
            this.pointer.end(undefined, {settle: true, immediateStop: true});
        }
        this.active = false;
        this.clutch = false;
    }
}
if (typeof module !== 'undefined') module.exports.WheelInput = WheelInput;
