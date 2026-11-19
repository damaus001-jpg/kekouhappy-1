// Reader lifecycle stays in this dynamic asset so existing servers can load it on F5.
class VideoConnection {
    constructor({selected = () => true, now = () => performance.now(),
        setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = id => clearTimeout(id)} = {}) {
        Object.assign(this, {selected, now, setTimer, clearTimer});
        this.state = 'connecting';
        this.startedAt = now(); this.lastFrameAt = null;
        this.failures = 0; this.timer = null; this.resume = null;
    }
    connected() { this.state = 'streaming'; this.connectedAt = this.now(); }
    frame() {
        this.lastFrameAt = this.now();
        // One cached bootstrap frame must not erase reconnect backoff.
        if (this.lastFrameAt - this.connectedAt >= 2000) this.failures = 0;
        this.state = 'streaming';
    }
    disconnected() { this.state = 'retrying'; }
    outageMs() { return this.now() - (this.lastFrameAt === null ? this.startedAt : this.lastFrameAt); }
    waitRetry() {
        this.failures++;
        const delay = this.failures === 1 ? 0 : Math.min(
            (this.selected() ? 100 : 500) * 2 ** Math.min(this.failures - 2, 5),
            this.selected() ? 1000 : 3000);
        return new Promise(resolve => {
            this.resume = resolve;
            this.timer = this.setTimer(() => { this.timer = null; this.resume = null; resolve(); }, delay);
        });
    }
    promote() {
        if (this.timer !== null) this.clearTimer(this.timer);
        this.timer = null;
        const resume = this.resume; this.resume = null;
        if (resume) resume();
    }
}
// Numeric metadata only; never record payloads, URLs, clipboard or error text.
const videoDiagnostics = {
    receivedAt: null, submittedAt: null, decodedAt: null, paintedAt: null, queue: 0,
    keyWaitAt: null, packets: 0, submitted: 0, decoded: 0, painted: 0, events: [], counts: {},
    mode: 'connecting', decoderState: 'unknown',
    record(reason) {
        this.counts[reason]=(this.counts[reason]||0)+1;
        this.events.push({at: performance.now(), reason});
        if (this.events.length > 128) this.events.shift();
    },
    snapshot() {
        const now = performance.now();
        return {at: now, receivedAt: this.receivedAt, submittedAt: this.submittedAt, decodedAt: this.decodedAt,
            paintedAt: this.paintedAt, queue: this.queue,
            keyWaitMs: this.keyWaitAt === null ? 0 : now - this.keyWaitAt,
            packets: this.packets, decoded: this.decoded, painted: this.painted,
            hidden: document.hidden, selected: batchSelected, connection: videoConnection.state,
            events: this.events.slice()};
    }
};
window.videoHealth = () => videoDiagnostics.snapshot();
// The dashboard keeps ready previews connected; draw once every three seconds.
const batchManaged = new URLSearchParams(location.search).has('batch');
let batchActive = !batchManaged;
let batchVisible = !batchManaged;
let batchSelected = !batchManaged;
let lastCanvasDrawAt = 0;
const BACKGROUND_DRAW_INTERVAL_MS = 3000;
const videoConnection = new VideoConnection({selected: () => !batchManaged || batchSelected});
let compatibleVideoAbort = null;
let nativeVideoAbort = null, videoStopped = false;
let videoSessionTask=null, lastSourcePackets=null;
const localReaderRecoveries=[];
const videoClientId=Math.random().toString(36).slice(2,14);
let videoReportBusy=false;
let videoReportTimer=null;
function observeSourceProgress(source){
    const packets=source.source_packets??source.rtp_packets;
    const sourceAge=source.source_au_age_ms??source.last_au_age_ms;
    const progressing=Number.isFinite(packets)&&lastSourcePackets!==null&&packets>lastSourcePackets&&Number.isFinite(sourceAge)&&sourceAge<1000;
    lastSourcePackets=packets;
    if(videoStopped||document.hidden||(batchManaged&&!batchSelected)||!progressing||videoConnection.state!=='streaming')return;
    const now=performance.now();
    if(videoDiagnostics.receivedAt===null||now-videoDiagnostics.receivedAt<4000)return;
    while(localReaderRecoveries.length&&now-localReaderRecoveries[0]>=60000)localReaderRecoveries.shift();
    if(localReaderRecoveries.length>=2||(localReaderRecoveries.length&&now-localReaderRecoveries.at(-1)<5000))return;
    localReaderRecoveries.push(now);
    videoDiagnostics.record('reader-no-progress');
    // The phone is demonstrably producing AUs, but this client has stopped
    // consuming. Cancel only this local fetch; never restart the phone source.
    if(videoDiagnostics.mode==='jpeg')compatibleVideoAbort?.abort();else nativeVideoAbort?.abort();
    videoConnection.disconnected();videoConnection.promote();
}
function sendVideoReport(){
    if(videoReportBusy||videoStopped)return;
    const now=performance.now(),age=value=>value===null?null:Math.max(0,Math.round(now-value));
    const report={client:videoClientId,mode:videoDiagnostics.mode,decoder_state:videoDiagnostics.decoderState,
        state:videoConnection.state,selected:batchSelected,hidden:document.hidden,
        pending_frame:!!pendingFrame,draw_scheduled:rafScheduled,
        receive_age_ms:age(videoDiagnostics.receivedAt),submit_age_ms:age(videoDiagnostics.submittedAt),
        decode_age_ms:age(videoDiagnostics.decodedAt),paint_age_ms:age(videoDiagnostics.paintedAt),
        queue:videoDiagnostics.queue,key_wait_ms:videoDiagnostics.keyWaitAt===null?0:age(videoDiagnostics.keyWaitAt),
        packets:videoDiagnostics.packets,submitted:videoDiagnostics.submitted,decoded:videoDiagnostics.decoded,painted:videoDiagnostics.painted,
        decode_errors:(videoDiagnostics.counts['sync-decode-error']||0)+(videoDiagnostics.counts['async-decode-error']||0),
        queue_resets:videoDiagnostics.counts['decode-queue-timeout']||0,reconnects:videoDiagnostics.counts['reader-retry']||0,
        paint_errors:videoDiagnostics.counts['paint-error']||0,paint_fallbacks:videoDiagnostics.counts['paint-timer-fallback']||0,
        key_timeouts:videoDiagnostics.counts['key-wait-timeout']||0,
        reader_resyncs:videoDiagnostics.counts['reader-no-progress']||0,
        page_restores:videoDiagnostics.counts['page-restored']||0};
    videoReportBusy=true;
    fetch('/video-health',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(report),signal:AbortSignal.timeout(3000)})
        .then(async response=>{
            if(response.ok)return response.json();
            // Older running phone services still expose read-only source
            // health; the local recovery guard can work before a reload.
            const health=await fetch('/video-health',{cache:'no-store',signal:AbortSignal.timeout(3000)});
            if(health.ok)return health.json();
        }).then(source=>{if(source)observeSourceProgress(source);})
        .catch(()=>{}).finally(()=>{videoReportBusy=false;});
}
function startVideoReports(){if(videoReportTimer===null)videoReportTimer=setInterval(sendVideoReport,2000);}
startVideoReports();
window.addEventListener('pagehide',()=>{clearInterval(videoReportTimer);videoReportTimer=null;});
let inputReady = !batchManaged, inputHealthPaused = false, inputMonitor = null, inputEpoch = 0;
function controlAvailable() { return batchActive && inputReady; }
if (batchManaged) document.body.classList.add('batch-preview', 'frame-on');
window.AUDIO_DEFAULT_ON = __AUDIO_DEFAULT_ON__;
// Resolution-collapse compensation default (server --compensate flag), with a
// per-load URL override for research: append ?compensate=0 / ?compensate=1.
window.COMPENSATE = (function () {
    const q = new URLSearchParams(location.search).get('compensate');
    if (q === '0' || q === 'false') return false;
    if (q === '1' || q === 'true') return true;
    return __COMPENSATE_DEFAULT__;
})();
// Lock the canvas buffer to the largest footprint seen and scale every frame
// to fill it, instead of resizing the canvas per frame. The device encoder
// oscillates displayHeight (2752<->2736) as the home indicator shows/hides;
// resizing on each toggle makes the whole <canvas> visibly shrink/expand --
// the "screen changing size" the user reports. Filling a fixed surface removes
// that (the <=0.6% scale is imperceptible), and a full-cover drawImage every
// frame leaves no stale GPU pixels (the old motion "tears" were really
// userspace-tunnel packet loss, gone on the kernel tunnel). Toggle: ?lockcanvas=0.
window.LOCKCANVAS = (function () {
    const q = new URLSearchParams(location.search).get('lockcanvas');
    if (q === '0' || q === 'false') return false;
    if (q === '1' || q === 'true') return true;
    return true;
})();
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');

// Size the canvas in CSS pixels so its display dimensions divide
// cleanly by devicePixelRatio -- on a 2x screen each backing-store
// pixel lands on one device pixel, giving the 1:1 native-resolution
// look while still fitting inside the viewport. When the viewport
// can't even fit the DPR-divided size we fall back to a further
// proportional shrink (still anchored to integer-ish device pixels
// where possible); image-rendering:high-quality keeps that fallback
// path from going visibly blocky.
const BEZEL_RATIO = 0.035;   // bezel width / screen short side
let reportedVideoSize='';
function fitCanvasToViewport() {
    if (!canvas.width || !canvas.height) return;
    const videoSize=canvas.width+'x'+canvas.height;
    if(batchManaged&&reportedVideoSize!==videoSize){
        reportedVideoSize=videoSize;
        parent.postMessage({type:'video-dimensions',width:canvas.width,height:canvas.height},
            new URLSearchParams(location.search).get('manager')||'http://127.0.0.1:8070');
    }
    const dpr = window.devicePixelRatio || 1;
    const naturalW = canvas.width / dpr;
    const naturalH = canvas.height / dpr;
    // Reserve room for the flanking trays, the stage padding (which also
    // holds the bezel's hardware buttons), the top bar and the dock. We
    // MEASURE the actual tray widths so collapse/uncollapse of either tray
    // immediately reclaims space for the canvas.
    const trayW = (id) => {
        const el = document.getElementById(id);
        return el ? el.getBoundingClientRect().width : 0;
    };
    const frameOn = batchManaged || document.body.classList.contains('frame-on');
    // The bezel is proportional to the displayed screen (see below), so it
    // takes a fixed share of the available box rather than a pixel count.
    const bezelShare = frameOn ? 1 + 2 * BEZEL_RATIO : 1;
    // Below the stacked-layout breakpoint (viewer.css) the trays sit under
    // the device and cost no width.
    const stacked = window.matchMedia('(max-width: 900px)').matches;
    const reservedW = (stacked ? 0 : trayW('left-tray') + trayW('right-tray')) + 48 + 40;
    const embeddedStage = document.getElementById('stage');
    const availW = batchManaged
        ? Math.max(1, embeddedStage.clientWidth - 4)
        : Math.max(100, window.innerWidth - reservedW) / bezelShare;
    const availH = batchManaged
        ? Math.max(1, embeddedStage.clientHeight - 4)
        : Math.max(100, window.innerHeight - 150) / bezelShare;
    // Embedded screens use the full stage and ignore standalone zoom preferences.
    const scale = batchManaged
        ? Math.min(availW / naturalW, availH / naturalH)
        : Math.min(1, availW / naturalW, availH / naturalH) * zoom;
    canvas.style.width  = (naturalW * scale) + 'px';
    canvas.style.height = (naturalH * scale) + 'px';
    canvas.style.transform = '';
    // Bezel geometry follows the displayed size so the frame looks the same
    // at every zoom level: screen corner radius, bezel width, button depth.
    const shortSide = Math.min(naturalW, naturalH) * scale;
    const frameStyle = document.getElementById('device-frame').style;
    frameStyle.setProperty('--screen-r', (shortSide * 0.125) + 'px');
    frameStyle.setProperty('--bezel', Math.max(5, shortSide * BEZEL_RATIO) + 'px');
    frameStyle.setProperty('--hw-t', Math.max(3, shortSide * 0.014) + 'px');
    zoomResetBtn.textContent = Math.round(zoom * 100) + '%';
    stageWrap.classList.toggle('zoomed', !batchManaged && zoom > 1);
}
window.addEventListener('resize', fitCanvasToViewport);

// ----- Zoom: a multiplier on top of the fit-to-window scale, so 1 always
// means "as large as fits" and survives window resizes / tray toggles.
// Persisted like the other view preferences.
const ZOOM_STEP = 1.2, ZOOM_MIN = 0.25, ZOOM_MAX = 4;
const zoomResetBtn = document.getElementById('zoom-reset');
const stageWrap = document.getElementById('stage-wrap');
let zoom = 1;
let batchScreenScale=1;
try {
    const saved = parseFloat(localStorage.getItem('zoom'));
    if (saved >= ZOOM_MIN && saved <= ZOOM_MAX) zoom = saved;
} catch (e) {}
function setZoom(value) {
    zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value));
    // Snap back onto exactly 1 so repeated in/out steps don't drift off "fit".
    if (Math.abs(zoom - 1) < 0.01) zoom = 1;
    try { localStorage.setItem('zoom', String(zoom)); } catch (e) {}
    fitCanvasToViewport();
}
document.getElementById('zoom-in').addEventListener('click', () => setZoom(zoom * ZOOM_STEP));
document.getElementById('zoom-out').addEventListener('click', () => setZoom(zoom / ZOOM_STEP));
zoomResetBtn.addEventListener('click', () => setZoom(1));
const statusEl = document.getElementById('status');
const fpsEl = document.getElementById('fps');
let frameCount = 0;
const lines = ['connecting...'];
function log(msg) {
    // Mirror to devtools so long lines aren't truncated by the
    // bottom-left status panel (which is intentionally compact).
    try { console.log('[serve-web]', msg); } catch (_) {}
    lines.push(msg); if (lines.length > 8) lines.shift(); render();
}
function render() { statusEl.textContent = `已解码帧数：${frameCount}\n` + lines.join('\n'); }
setInterval(render, 250);

// FPS readout. Sample frameCount once per second; the displayed number
// is the frame delta over the last 1 s. A stall shows up immediately
// as "0 fps" while the stream is still nominally "connected", which is
// what the status panel's `frames: N` counter doesn't make obvious.
let _fpsLastFc = 0;
let _fpsLastT = (typeof performance !== 'undefined') ? performance.now() : Date.now();
setInterval(() => {
    const now = (typeof performance !== 'undefined') ? performance.now() : Date.now();
    const dtSec = (now - _fpsLastT) / 1000;
    const dFrames = frameCount - _fpsLastFc;
    _fpsLastT = now;
    _fpsLastFc = frameCount;
    if (fpsEl) fpsEl.textContent = (dtSec > 0 ? (dFrames / dtSec) : 0).toFixed(1) + ' fps';
}, 1000);

function hex(u8, n=24) {
    let s = '';
    for (let i = 0; i < Math.min(u8.length, n); i++) s += u8[i].toString(16).padStart(2,'0');
    return s;
}

// ----- input: pointer -> /touch, hardware-buttons -> /button -----
// HID coords are UInt16 (0..65535) normalised across the device screen.
//
// `visualRotation` is how much the captured device buffer is rotated
// when drawn into the canvas (signed multiples of 90, CSS convention:
// positive = CW). The rotation lives INSIDE the canvas — i.e. we
// resize the canvas to the rotated footprint and call ctx.rotate before
// drawImage — so the canvas's CSS box already matches what the user
// sees and the surrounding flex layout / cosmetic bezel wrap it
// correctly even when the device is in landscape. touchCoords()
// therefore has to inverse-rotate clicks back into the device buffer's
// own coordinate system before normalising to HID 0..65535.
let visualRotation = 0;
function touchCoords(e) {
    const rect = canvas.getBoundingClientRect();
    // Click in canvas backing-store pixel space.
    const sx = (e.clientX - rect.left) * canvas.width  / rect.width;
    const sy = (e.clientY - rect.top)  * canvas.height / rect.height;
    const cw = canvas.width, ch = canvas.height;
    const sideways = Math.abs(visualRotation % 180) === 90;
    // Device buffer dims (un-rotated); canvas dims = rotated buffer dims.
    const dw = sideways ? ch : cw;
    const dh = sideways ? cw : ch;
    const dx = sx - cw / 2;
    const dy = sy - ch / 2;
    // Inverse of ctx.rotate(visualRotation): rotate the click by -visualRotation.
    const rad = -visualRotation * Math.PI / 180;
    const cos = Math.cos(rad), sin = Math.sin(rad);
    const bx = dx * cos - dy * sin + dw / 2;
    const by = dx * sin + dy * cos + dh / 2;
    return {
        x: Math.max(0, Math.min(65535, Math.round(bx / dw * 65535))),
        y: Math.max(0, Math.min(65535, Math.round(by / dh * 65535))),
    };
}

function reportManualInputFailure(path, error) {
    const message = error?.message || '控制输入失败，请检查手机连接';
    log(path + ' err: ' + message);
    if (batchManaged) {
        try {
            parent.postMessage({type: 'manual-input-result', ok: false, message},
                new URLSearchParams(location.search).get('manager') || 'http://127.0.0.1:8070');
        } catch (feedbackError) { log('控制失败提示未送达父页面：' + feedbackError.message); }
    }
}

async function postJson(path, payload) {
    // Note: do NOT pass {keepalive: true} -- that triggers fetch's
    // "send during page unload" path which has body-size limits and
    // queues requests differently; we want plain HTTP/1.1 keep-alive
    // (the default) so pointer events stream over one TCP.
    try {
        if (!controlAvailable()) throw Error('当前手机控制连接尚未就绪，请检查连接后重新操作');
        if (path === '/key') path = '/manual-key';
        if (path === '/touch') path = '/manual-touch';
        if (path === '/button' && payload.name === 'home' && payload.state === 'press') path = '/manual-home';
        const response = await fetch(path, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw Error('控制输入失败（HTTP ' + response.status + '）');
        return true;
    } catch (error) {
        reportManualInputFailure(path, error);
        inputMonitor?.invalidate();
        return false;
    }
}

let activePointer = null;
let foregroundPointerStart=null,foregroundDragReported=false,foregroundPointerMoved=false,foregroundPointerGesture=null,foregroundTapRevision=0;
function notifyForegroundActivity(kind){
    if(kind!=='tap-complete')foregroundTapRevision++;
    if(batchManaged&&batchSelected)parent.postMessage({type:'phone-activity',kind,keysHeld:pressedUsages.size>0},
        new URLSearchParams(location.search).get('manager')||'http://127.0.0.1:8070');
}
let lastCoords = {x: 0, y: 0};
const pointerInput = new PointerInput(async payload => {
    if (!controlAvailable()) throw Error('当前手机控制连接尚未就绪');
    const response = await fetch('/manual-touch', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload), signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw Error('触摸操作失败，请检查手机连接');
}, error => {activePointer = null; reportManualInputFailure('/manual-touch', error); inputMonitor?.invalidate();});
const wheelInput = new WheelInput(pointerInput, {
    bounds: () => canvas.getBoundingClientRect(),
    coords: touchCoords,
    enabled: () => controlAvailable() && activePointer === null,
});
canvas.addEventListener('wheel', event => {if(controlAvailable())notifyForegroundActivity('scroll');wheelInput.handle(event);}, {passive: false});
// Drag-outside-then-release leaves the device-side contact stuck if we
// only listen on the canvas: pointer capture is silently dropped on
// window blur / Cmd-Tab / right-click menus / OS-level interruptions,
// and the eventual pointerup then dispatches to whatever element the
// cursor is over (often nothing). Mirror up / cancel / lostcapture
// listeners onto `window` so we always see the release.
function releaseActive() {
    wheelInput.stop();
    if (activePointer === null) return;
    activePointer = null;
    foregroundPointerStart=null;
    notifyForegroundActivity('pointer-end');
    pointerInput.end(lastCoords);
}
canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;   // primary button only
    if (activePointer !== null) return;
    if (!controlAvailable()) {
        reportManualInputFailure('/manual-touch', Error('当前手机控制连接尚未就绪，请检查连接后重新操作'));
        inputMonitor?.invalidate();
        return;
    }
    pasteRevision++; // A new phone target cancels an unfinished paste.
    notifyForegroundActivity('pointer-start');
    foregroundTapRevision++;
    foregroundPointerStart={x:e.clientX,y:e.clientY};foregroundDragReported=false;foregroundPointerMoved=false;foregroundPointerGesture=null;
    wheelInput.stop();
    e.preventDefault();
    // preventDefault on pointerdown also suppresses the implicit
    // focus shift onto our tabindex=0 canvas; focus it explicitly so
    // a click on the canvas always (re)starts keyboard capture.
    canvas.focus({preventScroll: true});
    try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
    activePointer = e.pointerId;
    lastCoords = touchCoords(e);
    pointerInput.start(lastCoords);
    foregroundPointerGesture=pointerInput.gesture;
});
function onMove(e) {
    if (e.pointerId !== activePointer) return;
    if(foregroundPointerStart&&Math.hypot(e.clientX-foregroundPointerStart.x,e.clientY-foregroundPointerStart.y)>12)foregroundPointerMoved=true;
    if(foregroundPointerStart&&!foregroundDragReported&&Math.abs(e.clientY-foregroundPointerStart.y)>18){
        foregroundDragReported=true;notifyForegroundActivity('scroll');
    }
    e.preventDefault();
    lastCoords = touchCoords(e);
    pointerInput.move(lastCoords);
}
function onUp(e) {
    if (e.pointerId !== activePointer) return;
    const rect=canvas.getBoundingClientRect();
    const completedTap=e.type==='pointerup'&&foregroundPointerStart!==null&&!foregroundPointerMoved&&
        Math.hypot(e.clientX-foregroundPointerStart.x,e.clientY-foregroundPointerStart.y)<=12&&
        e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom;
    const gesture=foregroundPointerGesture;
    e.preventDefault();
    lastCoords = touchCoords(e);
    releaseActive();
    const tapRevision=foregroundTapRevision, tapEpoch=inputEpoch;
    if(completedTap&&gesture!==null){
        pointerInput.idle(gesture).then(async ok=>{
            if(!ok)return;
            await new Promise(resolve=>setTimeout(resolve,300));
            if(controlAvailable()&&batchSelected&&!document.hidden&&tapRevision===foregroundTapRevision&&tapEpoch===inputEpoch)notifyForegroundActivity('tap-complete');
        }).catch(()=>{});
    }
}
window.addEventListener('pointermove', onMove);
canvas.addEventListener('pointerup', onUp);
window.addEventListener('pointerup', onUp);
canvas.addEventListener('pointercancel', onUp);
window.addEventListener('pointercancel', onUp);
// `lostpointercapture` fires whenever capture is released for ANY
// reason (including the browser dropping it silently); use it as a
// final backstop so the contact never gets pinned indefinitely.
canvas.addEventListener('lostpointercapture', (e) => {
    if (e.pointerId === activePointer) releaseActive();
});
// Tab switch / window blur kills capture without firing up. Treat
// either as an implicit release so a stuck contact doesn't survive
// the user looking away.
window.addEventListener('blur', () => {foregroundTapRevision++;releaseActive();});
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') {foregroundTapRevision++;releaseActive();}
});
// Right-click on the phone image = Home button, matching the original control.
canvas.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    releaseActive();
    pointerInput.idle()
        .then(() => postJson('/button', {name: 'home', state: 'press'}))
        .then(ok => { if (ok) log('Home 请求已发送（右键），请核对手机画面'); })
        .catch(error => reportManualInputFailure('/manual-home', error));
});

document.querySelectorAll('button[data-btn]:not(.hw)').forEach(btn => {
    btn.addEventListener('click', () => {
        const name = btn.dataset.btn;
        postJson('/button', {name, state: 'press'}).then(ok => { if (ok) log('button request sent: ' + name); });
    });
});

// Bezel buttons behave like the physical ones: down while the pointer holds
// them, up on release. A tap on Power sleeps/wakes, a long press does whatever
// iOS does with a held button (Siri, volume repeat, ...).
const HW_MIN_HOLD_MS = 100;   // iOS ignores a down/up pair much shorter than a real tap
document.querySelectorAll('.hw[data-btn]').forEach(btn => {
    const name = btn.dataset.btn;
    const shown = (btn.getAttribute('aria-label') || name).toLowerCase();
    let downAt = 0;
    let chain = Promise.resolve();   // keeps down/up in order on the wire
    const release = () => {
        if (!downAt) return;
        const wait = Math.max(0, HW_MIN_HOLD_MS - (performance.now() - downAt));
        downAt = 0;
        chain = chain
            .then(() => new Promise(r => setTimeout(r, wait)))
            .then(() => postJson('/button', {name, state: 'up'}));
    };
    btn.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        try { btn.setPointerCapture(e.pointerId); } catch (_) {}
        downAt = performance.now();
        chain = chain.then(() => postJson('/button', {name, state: 'down'})).then(ok => { if (ok) log('button request sent: ' + shown); });
    });
    btn.addEventListener('pointerup', release);
    btn.addEventListener('pointercancel', release);
    btn.addEventListener('lostpointercapture', release);
    // Keyboard activation (Enter / Space on a focused button) has no hold.
    btn.addEventListener('click', (e) => {
        if (e.detail === 0) postJson('/button', {name, state: 'press'}).then(ok => { if (ok) log('button request sent: ' + shown); });
    });
});
window.addEventListener('blur', () => {
    // We won't see the pointerup once the window loses focus mid-press.
    document.querySelectorAll('.hw[data-btn]').forEach(btn => btn.dispatchEvent(new Event('pointercancel')));
});

// The bezel buttons are too thin to carry a caption, so their name shows in
// a tooltip next to the pointer as soon as it is over one (the native
// title tooltip takes a second to appear).
const hwTooltip = document.getElementById('hw-tooltip');
document.querySelectorAll('.hw').forEach(btn => {
    const place = (e) => {
        hwTooltip.style.left = (e.clientX + 14) + 'px';
        hwTooltip.style.top = (e.clientY + 14) + 'px';
    };
    btn.addEventListener('pointerenter', (e) => {
        hwTooltip.textContent = btn.dataset.label;
        hwTooltip.classList.remove('hidden');
        place(e);
    });
    btn.addEventListener('pointermove', place);
    btn.addEventListener('pointerleave', () => hwTooltip.classList.add('hidden'));
});

// Swipe synthesis: contact at the start edge, 10 intermediate
// contacts along the path, release at the end edge. ~200 ms total
// is in the same ballpark as a finger swipe, so iOS recognises it
// as a real gesture (faster gets misread as a flick + page snap,
// slower as a drag). Y stays at the vertical midpoint; X sweeps
// nearly edge-to-edge.
async function swipe(direction) {
    const yMid = 32768;
    const xStart = direction === 'left' ? 60000 : 5000;
    const xEnd   = direction === 'left' ? 5000  : 60000;
    const steps = 10;
    const dt = 20;  // ms between samples
    let contactAttempted = false, releaseAttempted = false, lastX = xStart;
    try {
        contactAttempted = true;
        if (!await postJson('/touch', {type: 'contact', x: xStart, y: yMid})) return false;
        for (let i = 1; i <= steps; i++) {
            lastX = Math.round(xStart + (xEnd - xStart) * (i / steps));
            await new Promise(r => setTimeout(r, dt));
            if (!await postJson('/touch', {type: 'contact', x: lastX, y: yMid})) return false;
        }
        releaseAttempted = true;
        if (!await postJson('/touch', {type: 'release', x: xEnd, y: yMid})) return false;
        log('swipe request sent: ' + direction);
        return true;
    } finally {
        // A failed contact response may still have pressed the phone. Release
        // once without replaying it; postJson still enforces control ownership.
        if (contactAttempted && !releaseAttempted) await postJson('/touch', {type: 'release', x: lastX, y: yMid});
    }
}
document.querySelectorAll('button[data-swipe]').forEach(btn => {
    btn.addEventListener('click', () => swipe(btn.dataset.swipe));
});

// Ctrl-hotkeys mirroring serve-vnc's _CTRL_COMBO_TO_HID:
//   Ctrl+H = Home, Ctrl+L = Lock, Ctrl+[ = Vol Down, Ctrl+] = Vol Up,
//   Ctrl+\ = Mute, Ctrl+S = Siri.
// Tooltips on the buttons advertise these. We use ctrlKey on every
// platform (Cmd is intercepted by browser shortcuts on macOS), match
// case-insensitively for letters, and preventDefault so we don't
// trigger the browser's own bindings (Ctrl+S = save, Ctrl+L = focus
// address bar in some browsers, etc.).
const CTRL_HOTKEYS = {
    'h': 'home',
    'l': 'lock',
    '[': 'volume-down',
    ']': 'volume-up',
    '\\': 'mute',
    's': 'siri',
};

// ----- input: physical key -> HID Keyboard usage -> /key -----
// KeyboardEvent.code is layout-independent (the physical key, not the
// typed character), which matches the HID usage table exactly. Anything
// not in this map is ignored.
const CODE_TO_HID = (() => {
    const m = {};
    for (let i = 0; i < 26; i++) m['Key' + String.fromCharCode(65 + i)] = 0x04 + i;
    // Digits: KeyboardEvent uses Digit1..Digit9, Digit0; HID uses 0x1E..0x26, then 0x27.
    for (let i = 1; i <= 9; i++) m['Digit' + i] = 0x1D + i;
    m['Digit0'] = 0x27;
    Object.assign(m, {
        Enter: 0x28, Escape: 0x29, Backspace: 0x2A, Tab: 0x2B, Space: 0x2C,
        Minus: 0x2D, Equal: 0x2E, BracketLeft: 0x2F, BracketRight: 0x30,
        Backslash: 0x31, Semicolon: 0x33, Quote: 0x34, Backquote: 0x35,
        Comma: 0x36, Period: 0x37, Slash: 0x38, CapsLock: 0x39,
        ArrowRight: 0x4F, ArrowLeft: 0x50, ArrowDown: 0x51, ArrowUp: 0x52,
        ShiftLeft: 0xE1, ShiftRight: 0xE5,
        ControlLeft: 0xE0, ControlRight: 0xE4,
        AltLeft: 0xE2, AltRight: 0xE6,
        MetaLeft: 0xE3, MetaRight: 0xE7,
    });
    for (let i = 1; i <= 12; i++) m['F' + i] = 0x39 + i;
    return m;
})();

const HID_KEY_V = 0x19;
const pressedUsages = new Set();
const windowsEditKeys = new Set();
function deviceKeyUsages(usages, windowsEdit) {
    if (!windowsEdit) return [...usages];
    const mapped = new Set([...usages].filter(u => u !== 0xE0 && u !== 0xE4));
    mapped.add(0xE3); // iOS Command; Windows Ctrl stays local to this editing chord.
    return [...mapped];
}
let lastKeyPost = Promise.resolve();
let enterSendPending = null;
let pastePending = false, pasteRevision = 0;
function postKeys() {
    // Serialize POSTs so the device sees them in order even when the
    // browser fires keydown bursts faster than the HTTP round-trip.
    const snapshot = deviceKeyUsages(pressedUsages, windowsEditKeys.size > 0);
    const epoch = inputEpoch;
    lastKeyPost = lastKeyPost.then(() => {if (epoch === inputEpoch) return postJson('/key', {usages: snapshot});});
}

function pasteFeedback(message) {
    clipboardResult(message);
    log(message);
    if (batchManaged) parent.postMessage({type: 'clipboard-paste-result', message},
        new URLSearchParams(location.search).get('manager') || 'http://127.0.0.1:8070');
}

function queueHostPaste(suppliedText = null) {
    notifyForegroundActivity('paste');
    if (pastePending) return Promise.reject(Error('正在粘贴，请稍候'));
    pastePending = true;
    const epoch = inputEpoch, revision = pasteRevision;
    const current = () => epoch === inputEpoch && revision === pasteRevision && keyboardCaptureOn();
    const task = lastKeyPost.then(async () => {
        if (!current()) throw Error('焦点或控制连接已变化，请重新粘贴');
        await pointerInput.idle();
        if (!current()) throw Error('焦点或控制连接已变化，请重新粘贴');
        pasteFeedback(suppliedText === null ? '正在读取电脑剪贴板…' : '正在准备粘贴到手机当前输入框…');
        const content = suppliedText === null ? await readHostClipboard() : {text: suppliedText, image: null};
        if (!current()) throw Error('焦点或控制连接已变化，请重新粘贴');
        if (!content.image && !content.text) throw Error('电脑剪贴板没有可粘贴的文字或图片');
        const response = await fetch(content.image ? '/clipboard/image' : '/clipboard', {
            method: 'POST',
            headers: {'Content-Type': content.image ? 'image/png' : 'application/json'},
            body: content.image || JSON.stringify({text: content.text}),
            signal: AbortSignal.timeout(10000),
        });
        if (!response.ok) throw Error('传到手机剪贴板失败（HTTP ' + response.status + '）');
        // Always write again on an explicit Ctrl+V, even if the same content was
        // pasted before: the phone clipboard may have changed in the meantime.
        lastShared = await fingerprint(content);
        if (!current()) throw Error('焦点或控制连接已变化，请重新粘贴');
        try {
            // The server dispatches one chord and releases it under one input lock.
            const result = await fetch('/manual-paste', {method: 'POST',
                headers: {'Content-Type': 'application/json'}, body: '{}',
                signal: AbortSignal.timeout(5000)});
            if (!result.ok) throw Error('手机粘贴按键未完成，请检查输入框');
        } catch (error) {
            if (epoch === inputEpoch && controlAvailable()) inputMonitor?.invalidate();
            throw error;
        }
        if (!current()) throw Error('控制目标已变化，粘贴结果请在原手机核对');
        pasteFeedback('粘贴快捷键已发出（' + (content.image ? '图片' : '文字') + '），请核对手机输入框；确认后再手动发送');
    });
    lastKeyPost = task.catch(error => pasteFeedback('粘贴未完成：' + (error.message || error)))
        .finally(() => { pastePending = false; });
    return task;
}

// Gate host-keystroke forwarding on canvas focus: keys flow to the
// device whenever the canvas owns the focus, and stop the moment the
// user clicks a button, the clipboard textarea, or anything else on
// the page chrome. No persisted toggle to flip — the focus is the
// state, and the #kb-indicator badge mirrors it visually.
const kbIndicator = document.getElementById('kb-indicator');
function keyboardCaptureOn() { return controlAvailable() && document.activeElement === canvas; }
function releaseAllKeys() {
    enterSendPending = null;
    pasteRevision++;
    windowsEditKeys.clear();
    if (pressedUsages.size) {
        pressedUsages.clear();
        postKeys();
    }
    notifyForegroundActivity('key-state');
}
function updateKbIndicator() {
    kbIndicator.classList.toggle('hidden', !keyboardCaptureOn());
}
canvas.addEventListener('focus', updateKbIndicator);
canvas.addEventListener('blur', () => {
    // Dropping focus must release any held keys immediately — we
    // won't see the keyup once events stop being forwarded.
    releaseAllKeys();
    updateKbIndicator();
});
updateKbIndicator();

// Help modal: opened by '?' (or the '?' button), dismissed by Esc /
// click outside / close-X. The shortcut works regardless of the
// keyboard-capture toggle so the user can always reach it; while the
// modal is open we gate all forwarding to the device so typing into
// the page doesn't leak through.
const helpOverlay = document.getElementById('help-overlay');
function setHelpOpen(open) {
    helpOverlay.classList.toggle('hidden', !open);
    helpOverlay.setAttribute('aria-hidden', open ? 'false' : 'true');
}
function helpIsOpen() { return !helpOverlay.classList.contains('hidden'); }
document.getElementById('help-toggle').addEventListener('click', () => setHelpOpen(true));
document.getElementById('help-close').addEventListener('click', () => setHelpOpen(false));
helpOverlay.addEventListener('click', (e) => {
    // Click on the dimmed backdrop (outside the modal card) closes.
    if (e.target === helpOverlay) setHelpOpen(false);
});

window.addEventListener('keydown', (e) => {
    // '?' always opens help; Esc closes it. Both pre-empt the
    // keyboard-capture gate so they work even when capture is off
    // (and when on, we don't also forward shift+/ to the device).
    if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setHelpOpen(true);
        return;
    }
    if (e.key === 'Escape' && helpIsOpen()) {
        e.preventDefault();
        setHelpOpen(false);
        return;
    }
    // While help is open the device shouldn't see any keystrokes.
    if (helpIsOpen()) { e.preventDefault(); return; }
    // Local hotkeys (handled in the browser, never forwarded to the
    // device) -- run BEFORE the keyboard-capture gate so they work
    // regardless of whether forwarding is on.
    if (e.ctrlKey && !e.altKey && !e.metaKey && e.key.length === 1) {
        const k = e.key.toLowerCase();
        if (k === 'p') { e.preventDefault(); takeScreenshot(); return; }
        if (k === '=' || k === '+') { e.preventDefault(); setZoom(zoom * ZOOM_STEP); return; }
        if (k === '-') { e.preventDefault(); setZoom(zoom / ZOOM_STEP); return; }
        if (k === '0') { e.preventDefault(); setZoom(1); return; }
    }
    if (!keyboardCaptureOn()) return;
    notifyForegroundActivity('key');
    // Ctrl-hotkey path consumes the event; don't also type it.
    if (e.ctrlKey && !e.altKey && !e.metaKey) {
        const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
        const name = CTRL_HOTKEYS[key];
        if (name) {
            e.preventDefault();
            postJson('/button', {name, state: 'press'}).then(ok => { if (ok) log('hotkey request sent: ' + name); });
            return;
        }
    }
    const usage = CODE_TO_HID[e.code];
    if (usage === undefined) return;
    e.preventDefault();
    if (e.repeat) return;            // host autorepeat -- the device does its own
    // An explicit paste is independent of background clipboard sync. Consume V
    // here so a failed clipboard transfer cannot paste stale phone contents.
    const ctrlHeld = pressedUsages.has(0xE0) || pressedUsages.has(0xE4);
    if (usage === HID_KEY_V && (e.metaKey || e.ctrlKey || ctrlHeld) && !e.altKey) {
        queueHostPaste().catch(() => {});
        return;
    }
    if (e.ctrlKey && !e.metaKey && !e.altKey && ['KeyC', 'KeyV', 'KeyX', 'KeyA'].includes(e.code)) {
        windowsEditKeys.add(usage);
    }
    if (!pressedUsages.has(usage)) {
        pressedUsages.add(usage);
        postKeys();
        if(usage===0x28&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!e.shiftKey){
            enterSendPending={epoch:inputEpoch,down:lastKeyPost};
        }
        notifyForegroundActivity('key-state');
    }
});
window.addEventListener('keyup', (e) => {
    if (helpIsOpen() || !keyboardCaptureOn()) return;
    const usage = CODE_TO_HID[e.code];
    if (usage === undefined) return;
    e.preventDefault();
    windowsEditKeys.delete(usage);
    const sentEnter=usage===0x28?enterSendPending:null;
    if(usage===0x28)enterSendPending=null;
    if (pressedUsages.delete(usage)) postKeys();
    notifyForegroundActivity('key-state');
    if(sentEnter){
        const revision=foregroundTapRevision,release=lastKeyPost;
        Promise.all([sentEnter.down,release]).then(async results=>{
            if(!results.every(ok=>ok===true))return;
            await new Promise(resolve=>setTimeout(resolve,300));
            if(sentEnter.epoch===inputEpoch&&revision===foregroundTapRevision&&
                keyboardCaptureOn()&&pressedUsages.size===0&&!document.hidden){
                notifyForegroundActivity('send-complete');
            }
        }).catch(()=>{});
    }
});
window.addEventListener('blur', () => {
    // Window-blur means we won't see keyup; flush the bitmap so no
    // key ends up stuck-down on the device.
    releaseAllKeys();
});

// ----- Orientation: POST /rotate with {direction: 'left'|'right'} and
// keep the canvas in sync with the device's reported state.
// Updating `visualRotation` triggers an immediate redraw of the most-
// recent video frame at the new orientation (no wait for the next
// decoded frame). If iOS subsequently re-renders the buffer in the
// new orientation (its aspect ratio flips between portrait and
// landscape), drawPending() auto-resets the rotation to 0 to avoid
// double-rotating the now-natively-oriented content.
const deviceFrameEl = document.getElementById('device-frame');
function setVisualRotation(deg) {
    deg = ((deg % 360) + 540) % 360 - 180;  // normalise to (-180, 180]
    if (deg === visualRotation) return;
    // Pick the shortest signed delta around the circle so a 180 ->
    // -180 transition doesn't sweep the long way around.
    let delta = deg - visualRotation;
    if (delta > 180) delta -= 360;
    if (delta < -180) delta += 360;
    visualRotation = deg;
    deviceFrameEl.dataset.rot = String(deg);   // moves the bezel's hardware buttons
    // Canvas-internal rotation snaps immediately (so dim swap + layout
    // reflow happen now), then the device-frame's CSS transform is
    // set to -delta degrees so the *visual* position matches where
    // the canvas was a moment ago. We then animate the transform
    // back to identity, giving a smooth perceived rotation while the
    // surrounding layout has already moved.
    redrawWithCurrentRotation();
    deviceFrameEl.style.transition = 'none';
    deviceFrameEl.style.transform = `rotate(${-delta}deg)`;
    // Two RAFs to make sure the no-transition initial transform paints
    // before we install the animating transition; one RAF is usually
    // enough but two is safer across browsers.
    requestAnimationFrame(() => requestAnimationFrame(() => {
        deviceFrameEl.style.transition = 'transform 0.3s cubic-bezier(.4,0,.2,1)';
        deviceFrameEl.style.transform = '';
    }));
}
// Device-reported orientation -> in-canvas rotation that mirrors how
// the user is physically holding the device. landscapeLeft means the
// device is tilted 90° CCW (home button on the right), so the captured
// buffer content rotates CCW in the canvas (-90) — the device's top
// edge ends up on the left of the canvas just like in the user's view.
const ORIENTATION_DEGREES = {
    portrait: 0,
    landscapeLeft: -90,
    portraitUpsideDown: 180,
    landscapeRight: 90,
};
async function postRotate(direction) {
    setVisualRotation(visualRotation + (direction === 'left' ? -90 : 90));
    try {
        const r = await fetch('/rotate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({direction}),
        });
        if (!r.ok) { log('rotate HTTP ' + r.status); return; }
        const j = await r.json();
        const target = ORIENTATION_DEGREES[j.currentDeviceOrientation];
        if (typeof target === 'number') setVisualRotation(target);
        log('rotate: ' + j.currentDeviceOrientation);
    } catch (e) { log('rotate err: ' + (e.message || e)); }
}
document.getElementById('rotate-left').addEventListener('click', () => postRotate('left'));
document.getElementById('rotate-right').addEventListener('click', () => postRotate('right'));

// ----- Screenshot: save what's drawn into the canvas as a PNG.
// Reads the existing backing store (including any in-canvas rotation),
// so the file matches what the user sees -- no extra server round-trip.
function tsStamp() {
    const d = new Date();
    const z = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${z(d.getMonth()+1)}${z(d.getDate())}-${z(d.getHours())}${z(d.getMinutes())}${z(d.getSeconds())}`;
}
function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function takeScreenshot() {
    if (!canvas.width || !canvas.height) { log('screenshot: canvas empty'); return; }
    canvas.toBlob((blob) => {
        if (!blob) { log('screenshot: toBlob returned null'); return; }
        const name = `screenshot-${tsStamp()}.png`;
        downloadBlob(blob, name);
        log('saved ' + name);
    }, 'image/png');
}
document.getElementById('screenshot').addEventListener('click', takeScreenshot);

// ----- Reload window: full page reload. Useful when something is stuck
// and Force Restart (which only restarts the device-side stream) isn't
// enough.
document.getElementById('reload-window').addEventListener('click', () => {
    log('reloading page…');
    setTimeout(() => location.reload(), 50);
});

// ----- Collapsible side trays. Persist the open/closed state per tray
// so the layout survives a reload. Each tray button has data-tray=
// {"left","right"}.
function applyTrayState(side) {
    const el = document.getElementById(side + '-tray');
    if (!el) return;
    let collapsed = false;
    try { collapsed = localStorage.getItem('tray-' + side) === 'collapsed'; } catch (e) {}
    el.classList.toggle('collapsed', collapsed);
}
function toggleTray(side) {
    const el = document.getElementById(side + '-tray');
    if (!el) return;
    const collapsed = !el.classList.contains('collapsed');
    el.classList.toggle('collapsed', collapsed);
    try { localStorage.setItem('tray-' + side, collapsed ? 'collapsed' : 'open'); } catch (e) {}
    fitCanvasToViewport();
}
applyTrayState('left'); applyTrayState('right');
document.querySelectorAll('.tray-toggle').forEach(btn => {
    btn.addEventListener('click', () => toggleTray(btn.dataset.tray));
});

// ----- Force Restart: drop the current video stream + reload the page.
// Wipes all client-side state and pulls a fresh IDR from a new stream.
document.getElementById('restart').addEventListener('click', async () => {
    log('forcing restart + reload...');
    try {
        await fetch('/restart', {method: 'POST', cache: 'no-store'});
    } catch (e) { log('restart err: ' + e.message); }
    setTimeout(() => location.reload(), 100);
});

// ----- Dark / light toggle: GET /style reads the current style,
// POST /style with {"style":"dark"|"light"} flips it. Button label
// shows the CURRENT style so the click reads as "toggle to the other".
const styleBtn = document.getElementById('style-toggle');
function setStyleLabel(s) { styleBtn.dataset.style = s; styleBtn.textContent = '外观：' + (s === 'dark' ? '深色' : '浅色'); }
async function refreshStyle() {
    try {
        const r = await fetch('/style', {cache: 'no-store'});
        if (!r.ok) return;
        const j = await r.json();
        if (j && j.style) setStyleLabel(j.style);
    } catch (e) { log('style get err: ' + (e.message || e)); }
}
styleBtn.addEventListener('click', async () => {
    const cur = styleBtn.dataset.style;
    const next = cur === 'dark' ? 'light' : 'dark';
    try {
        const r = await fetch('/style', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({style: next}),
        });
        if (r.ok) { setStyleLabel(next); log('style: ' + next); }
        else { log('style set HTTP ' + r.status); }
    } catch (e) { log('style set err: ' + (e.message || e)); }
});
refreshStyle();

// ----- Frame toggle: pure-cosmetic CSS bezel around the canvas.
// Persisted in localStorage so a reload keeps the user's choice.
const frameBtn = document.getElementById('frame-toggle');
function setFrameLabel() {
    const on = document.body.classList.contains('frame-on');
    frameBtn.textContent = '边框：' + (on ? '显示' : '隐藏');
    frameBtn.classList.toggle('active', on);
}
try {
    if (!batchManaged && localStorage.getItem('frameOn') === 'false') document.body.classList.remove('frame-on');
} catch (e) {}
setFrameLabel();
frameBtn.addEventListener('click', () => {
    const on = document.body.classList.toggle('frame-on');
    setFrameLabel();
    fitCanvasToViewport();
    try { localStorage.setItem('frameOn', on ? 'true' : 'false'); } catch (e) {}
});

// ----- Sound toggle: connect to /audio.bin which streams PRE-DECODED
// PCM (s16le, 48 kHz, stereo interleaved). The server uses pyav's
// aac_at codec (macOS AudioToolbox, hardware-backed) to decode AAC-ELD
// because Chrome's WebCodecs doesn't recognise mp4a.40.39 -- AAC-ELD
// isn't in its supported AAC object types. Decoding host-side is
// trivially cheap and adds ~1.5 Mbps over localhost.
let audioCtx = null;
let audioAbort = null;
let audioActive = false;
let audioReconnectPending = false;
const soundBtn = document.getElementById('sound-toggle');

async function startAudio() {
    if (audioActive) return;
    audioActive = true;
    soundBtn.textContent = '关闭声音';
    audioAbort = new AbortController();
    try {
        audioCtx = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' });
        await audioCtx.resume();
    } catch (e) { log('audioCtx err: ' + e.message); stopAudio(); return; }
    // Playout scheduling. AAC-ELD arrives in 10 ms AUs; we schedule each buffer
    // back-to-back from `nextStart`. Keep the baseline latency low but leave
    // enough cushion to ride out normal network/UI jitter.
    const AUDIO_PRIME_SECS = 0.06;   // initial buffer before the first AU plays
    const AUDIO_UNDERRUN_SECS = 0.04; // re-prime after we fall behind
    const AUDIO_MAX_LATENCY_SECS = 0.18; // trim back once drift pushes us past this
    let nextStart = audioCtx.currentTime + AUDIO_PRIME_SECS;
    let totalSamples = 0;

    const playPcm = (pcmBytes) => {
        // pcmBytes is interleaved int16 little-endian, stereo, 48 kHz.
        const i16 = new Int16Array(pcmBytes.buffer, pcmBytes.byteOffset,
                                   pcmBytes.byteLength >> 1);
        const frames = i16.length >> 1; // 2 channels
        if (frames === 0) return;
        const buf = audioCtx.createBuffer(2, frames, 48000);
        const left = buf.getChannelData(0);
        const right = buf.getChannelData(1);
        const INV = 1 / 32768;
        for (let i = 0, j = 0; i < frames; i++, j += 2) {
            left[i] = i16[j] * INV;
            right[i] = i16[j + 1] * INV;
        }
        const src = audioCtx.createBufferSource();
        src.buffer = buf;
        src.connect(audioCtx.destination);
        const now = audioCtx.currentTime;
        if (nextStart < now) {
            // Schedule fell behind (UI stall) -- jump forward to keep going.
            nextStart = now + AUDIO_UNDERRUN_SECS;
        } else if (nextStart - now > AUDIO_MAX_LATENCY_SECS) {
            // Latency crept up (clock drift between the device's audio rate and
            // the AudioContext clock). Trim back toward the prime target so the
            // sound stays in sync instead of only ever growing more delayed.
            nextStart = now + AUDIO_PRIME_SECS;
        }
        src.start(nextStart);
        nextStart += buf.duration;
        totalSamples += frames;
    };

    try {
        const resp = await fetch('/audio.bin', { signal: audioAbort.signal });
        if (!resp.ok) {
            const body = await resp.text();
            log('audio HTTP ' + resp.status + ': ' + body.trim());
            stopAudio();
            return;
        }
        const reader = resp.body.getReader();
        let buf = new Uint8Array(0);
        log('audio stream open');
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const merged = new Uint8Array(buf.length + value.length);
            merged.set(buf); merged.set(value, buf.length);
            buf = merged;
            while (buf.length >= 4) {
                const len = (buf[0]<<24)|(buf[1]<<16)|(buf[2]<<8)|buf[3];
                if (buf.length < 4 + len) break;
                const pcmBytes = buf.slice(4, 4 + len);
                buf = buf.subarray(4 + len);
                if (!pcmBytes.length) continue;
                try { playPcm(pcmBytes); }
                catch (e) { log('audio play err: ' + e.message); }
            }
        }
    } catch (e) {
        if (e.name !== 'AbortError') log('audio fetch err: ' + e.message);
    }
    log('audio stream closed (' + totalSamples + ' samples)');
    // If we didn't stop voluntarily (e.g. server tore down audio after a
    // /restart), auto-reconnect after a short delay -- iOS needs ~1 s
    // between sessions to come back cleanly. The reconnect is cancelled
    // if the user clicks Disable Sound in the interim.
    const wasActive = audioActive;
    audioActive = false;
    soundBtn.textContent = '开启声音';
    if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
    audioAbort = null;
    if (wasActive) {
        audioReconnectPending = true;
        log('audio: auto-reconnecting in 1 s');
        setTimeout(() => {
            if (audioReconnectPending) {
                audioReconnectPending = false;
                startAudio();
            }
        }, 1000);
    }
}

function stopAudio() {
    audioActive = false;
    audioReconnectPending = false;
    soundBtn.textContent = '开启声音';
    if (audioAbort) { try { audioAbort.abort(); } catch (_) {} audioAbort = null; }
    if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
}

soundBtn.addEventListener('click', () => {
    if (audioActive) stopAudio(); else startAudio();
});

// AUDIO_DEFAULT_ON is templated by the server at request time (replaced
// in the HTML body by the /index.html handler). When true, we start the
// audio pipeline immediately so the browser is already buffering PCM by
// the time the user does something -- their first gesture resumes the
// suspended AudioContext and they hear audio with no extra clicks.
if (window.AUDIO_DEFAULT_ON) {
    startAudio();
    function resumeAudioOnGesture() {
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume().then(() => log('audio resumed (state=' + audioCtx.state + ')'));
        }
    }
    ['pointerdown', 'click', 'keydown', 'touchstart'].forEach(ev => {
        document.addEventListener(ev, resumeAudioOnGesture, { capture: true });
    });
}

async function fetchCodecWithRetry() {
    // /codec triggers a device-side stream restart on first call -- on a
    // cold daemon that can take 6-10 s, and sometimes the RemoteXPC
    // handshake just fails outright. Retry with backoff so a transient
    // failure doesn't leave the viewer permanently dead.
    const delays = [200, 500, 1000, 2000, 3000, 4000];
    let lastErr = '';
    for (let attempt = 0; attempt <= delays.length; attempt++) {
        if (attempt > 0) {
            log('codec retry #' + attempt + ' in ' + delays[attempt - 1] + 'ms (' + lastErr + ')');
            await new Promise(r => setTimeout(r, delays[attempt - 1]));
        }
        try {
            const resp = await fetch('/codec', { cache: 'no-store', signal: AbortSignal.timeout(15000) });
            if (!resp.ok) { lastErr = 'HTTP ' + resp.status; continue; }
            // /codec returns JSON: {codec, description} where description is a
            // base64 hvcC record (HEVCDecoderConfigurationRecord). Passing it
            // as the decoder `description` selects hvcC-mode decoding (matching
            // the length-prefixed NALU framing on /stream.bin), which avoids
            // Chrome's Annex-B path that tears under motion.
            const info = await resp.json();
            if (!info.codec || !info.description) { lastErr = 'incomplete codec info (params not yet seen)'; continue; }
            const description = Uint8Array.from(atob(info.description), c => c.charCodeAt(0));
            return { codec: info.codec.trim(), description };
        } catch (e) {
            lastErr = e.message || String(e);
        }
    }
    throw new Error('codec unreachable after retries: ' + lastErr);
}

// vsync-aligned draw: the decoder's output callback only stores the
// latest frame; the actual ctx.drawImage call lives in a
// requestAnimationFrame loop so the compositor never reads the canvas
// mid-update. Older queued frames are .close()'d so we don't leak GPU
// memory — we always show the most recent decoded frame.
let pendingFrame = null;
let rafScheduled = false;
let frameDrawTimer = null, frameDrawRaf = null, lastDecodedFrameAt = 0;
function cancelFrameDraw() {
    if (frameDrawTimer !== null) clearTimeout(frameDrawTimer);
    if (frameDrawRaf !== null) cancelAnimationFrame(frameDrawRaf);
    frameDrawTimer = frameDrawRaf = null;
    rafScheduled = false;
}
function scheduleFrameDraw() {
    if (rafScheduled || !pendingFrame) return;
    rafScheduled = true;
    if (batchManaged && !batchSelected) {
        // display:none iframes suspend rAF. A timer keeps their latest canvas
        // warm without drawing more than once every three seconds.
        frameDrawTimer = setTimeout(() => { frameDrawTimer = null; drawPending(); },
            Math.max(0, BACKGROUND_DRAW_INTERVAL_MS - (performance.now() - lastCanvasDrawAt)));
    } else {
        frameDrawRaf = requestAnimationFrame(() => {
            frameDrawRaf=null;
            if(frameDrawTimer!==null)clearTimeout(frameDrawTimer);
            frameDrawTimer=null;drawPending();
        });
        frameDrawTimer=setTimeout(()=>{
            frameDrawTimer=null;
            if(document.hidden)return;
            if(frameDrawRaf!==null)cancelAnimationFrame(frameDrawRaf);
            frameDrawRaf=null;
            if(pendingFrame)videoDiagnostics.record('paint-timer-fallback');
            drawPending();
        },150);
    }
}
function queueVideoFrame(frame) {
    videoDiagnostics.decodedAt = performance.now(); videoDiagnostics.decoded++;
    if (pendingFrame) { try { pendingFrame.close(); } catch (_) {} }
    pendingFrame = frame;
    lastDecodedFrameAt = performance.now();
    frameCount++;
    videoConnection.frame();
    offlineOverlay.classList.add('hidden');
    scheduleFrameDraw();
}
function setBatchVideoSelected(selected) {
    if (batchSelected === selected) return;
    batchSelected = selected;
    cancelFrameDraw();
    if (selected) {
        videoConnection.promote();
        fitCanvasToViewport();
        // Present the latest decoded frame immediately; do not wait for a
        // previously suspended background rAF or the next incoming frame.
        if (pendingFrame) drawPending();
        else redrawWithCurrentRotation();
        if (frameCount > 0 && performance.now() - lastDecodedFrameAt < OFFLINE_GRACE_SECS * 1000) {
            offlineOverlay.classList.add('hidden');
            _lastFc = frameCount; _stableSec = _nextPliSec = _nextRestartSec = 0;
        }
    }
    scheduleFrameDraw();
}
function resumeVideoDraw(){
    if(document.hidden||(batchManaged&&!batchSelected))return;
    cancelFrameDraw();
    if(pendingFrame)drawPending(true);else redrawWithCurrentRotation();
    scheduleFrameDraw();
}
// The most recent decoded VideoFrame, kept alive so we can redraw it
// at a new rotation without waiting for the next decode. Closed when
// it's replaced or when the page is unloaded.
let lastFrame = null;
// Last frame's buffer-aspect orientation (true = landscape, false =
// portrait). When iOS re-renders after a rotation the buffer aspect
// flips — that signals the content is now natively oriented in the
// buffer, so we drop our in-canvas rotation to avoid double-rotating.
let lastFrameLandscape = null;
document.addEventListener('visibilitychange',()=>{if(!document.hidden){videoConnection.promote();resumeVideoDraw();}});
window.addEventListener('focus',resumeVideoDraw);
canvas.addEventListener('contextrestored',resumeVideoDraw);

// ----- Resolution-collapse compensation. Under rapid motion the device
// encoder drops to a smaller capture resolution (observed 720x1280 for a
// 1264x2752 panel) rendered into the TOP-LEFT of the fixed buffer with the
// rest flat gray (Y=Cb=Cr=128) padding -- the "screen shrinks to a corner
// while swiping" tear. It's in the bitstream (device-side, under the ~6 Mbps
// cap) and can't be prevented from our side. But the shrunk region is the
// whole screen, just stretched into fewer pixels -- so we detect that content
// rectangle and stretch it back to fill the canvas. The collapse then reads
// as a momentary softness dip in a correctly-placed full-frame image instead
// of a jarring corner shrink.
//
// Detection runs on the RAW decoded frame (never the already-compensated
// canvas -- that would feed back and oscillate), throttled and cached. The
// content is top-left anchored so the crop origin is always (0,0); we find
// the right/bottom padding boundary. Validated offline against real collapsed
// captures: full-size on clean frames, ~720x1280 on collapsed ones.
const _detCanvas = document.createElement('canvas');
const _detCtx = _detCanvas.getContext('2d', {willReadFrequently: true});
let _cropSrcW = 0, _cropSrcH = 0;   // 0 => draw the full frame (not collapsed)
let _lockW = 0, _lockH = 0;         // locked canvas footprint (max seen); see window.LOCKCANVAS
const DET_H = 344;                  // downsample height for detection
function detectContentCrop(f) {
    const fw = f.displayWidth, fh = f.displayHeight;
    if (!fw || !fh) return;
    const DW = Math.max(8, Math.round(DET_H * fw / fh));
    // Reuse the readback surface; assigning even an unchanged size resets it.
    if (_detCanvas.width !== DW) _detCanvas.width = DW;
    if (_detCanvas.height !== DET_H) _detCanvas.height = DET_H;
    try {
        _detCtx.drawImage(f, 0, 0, DW, DET_H);
        const d = _detCtx.getImageData(0, 0, DW, DET_H).data;
        const isGray = (x, y) => { const i = (y * DW + x) * 4;
            return Math.abs(d[i] - 128) < 6 && Math.abs(d[i + 1] - 128) < 6 && Math.abs(d[i + 2] - 128) < 6; };
        // Last column / row that still holds content (<60% gray padding).
        let cr = 0;
        for (let x = 0; x < DW; x++) { let g = 0, n = 0;
            for (let y = 0; y < DET_H; y += 4) { n++; if (isGray(x, y)) g++; }
            if (g / n < 0.6) cr = x; }
        let cb = 0;
        for (let y = 0; y < DET_H; y++) { let g = 0, n = 0;
            for (let x = 0; x < DW; x += 4) { n++; if (isGray(x, y)) g++; }
            if (g / n < 0.6) cb = y; }
        // Map back to source px, biasing one cell inward so a boundary cell
        // that straddles content+padding doesn't leave a gray sliver.
        const cw = Math.round((cr / DW) * fw);
        const ch = Math.round((cb / DET_H) * fh);
        // Compensate only on a clear collapse (both dims well under full and
        // not degenerate); otherwise draw the full frame untouched.
        if (cw > fw * 0.2 && cw < fw * 0.92 && ch > fh * 0.2 && ch < fh * 0.92) {
            _cropSrcW = cw; _cropSrcH = ch;
        } else {
            _cropSrcW = 0; _cropSrcH = 0;
        }
    } catch (_) { /* transient readback failure -- keep previous crop */ }
}

function drawFrame(f) {
    if(ctx.isContextLost?.())throw Error('canvas context lost');
    const sideways = Math.abs(visualRotation % 180) === 90;
    const fw = f.displayWidth, fh = f.displayHeight;
    const targetW = sideways ? fh : fw;
    const targetH = sideways ? fw : fh;
    if (window.LOCKCANVAS) {
        // Grow-only: keep the canvas at the largest footprint seen so the
        // encoder's 2752<->2736 oscillation never resizes it (no shrink).
        // The lock is per orientation: a portrait<->landscape flip (Rotate, or
        // iOS re-rendering the buffer) must start over, or the max of both
        // footprints is a square that the frame gets stretched into.
        if ((targetW > targetH) !== (_lockW > _lockH)) _lockW = _lockH = 0;
        if (targetW > _lockW || targetH > _lockH) {
            _lockW = Math.max(_lockW, targetW);
            _lockH = Math.max(_lockH, targetH);
            canvas.width = _lockW;
            canvas.height = _lockH;
            fitCanvasToViewport();
        }
    } else if (targetW !== canvas.width || targetH !== canvas.height) {
        canvas.width = targetW;
        canvas.height = targetH;
        fitCanvasToViewport();
    }
    // Source rect: the detected content region on collapse, else the whole
    // frame. Stretched to fill the canvas footprint (un-doing any device
    // shrink AND the 16px height oscillation) inside the rotation transform.
    const dstW = canvas.width, dstH = canvas.height;
    const srcW = _cropSrcW || fw;
    const srcH = _cropSrcH || fh;
    const fpW = sideways ? dstH : dstW;   // unrotated footprint that fills the
    const fpH = sideways ? dstW : dstH;   // canvas after the rotation transform
    ctx.save();
    ctx.translate(dstW / 2, dstH / 2);
    if (visualRotation) ctx.rotate(visualRotation * Math.PI / 180);
    ctx.drawImage(f, 0, 0, srcW, srcH, -fpW / 2, -fpH / 2, fpW, fpH);
    ctx.restore();
}
function redrawWithCurrentRotation() {
    if (lastFrame) drawFrame(lastFrame);
}
function drawPending(force = false) {
    rafScheduled = false;
    const f = pendingFrame;
    pendingFrame = null;
    if (!f) return;
    // Keep every warm viewer decoding so selection can show its newest frame,
    // but repaint non-selected canvases at most once every three seconds.
    const now = performance.now();
    if (!force && batchManaged && !batchSelected && now - lastCanvasDrawAt < BACKGROUND_DRAW_INTERVAL_MS) {
        try { f.close(); } catch (_) {}
        return;
    }
    lastCanvasDrawAt = now;
    const landscape = f.displayWidth > f.displayHeight;
    if (lastFrameLandscape !== null && landscape !== lastFrameLandscape && visualRotation !== 0) {
        // iOS rerendered the buffer in the new orientation — content is
        // now natively upright, so drop our in-canvas rotation.
        visualRotation = 0;
        deviceFrameEl.dataset.rot = '0';
    }
    lastFrameLandscape = landscape;
    // Detect the collapse-crop rectangle from THIS raw frame, every frame:
    // the stream flips between collapsed and full-res frames faster than any
    // throttle, so a cached crop applied to a mismatched frame zooms a full
    // frame into its top-left (the "smaller screen over the old full screen"
    // artifact). Per-frame detection keeps the crop matched to the frame.
    if (window.COMPENSATE) detectContentCrop(f); else { _cropSrcW = 0; _cropSrcH = 0; }
    try {
        drawFrame(f);
        videoDiagnostics.paintedAt = performance.now(); videoDiagnostics.painted++;
    } catch (e) {
        videoDiagnostics.record('paint-error');
        log('draw err: ' + (e.message || e));
    }
    if (lastFrame && lastFrame !== f) {
        try { lastFrame.close(); } catch (_) {}
    }
    lastFrame = f;
}

// A static/quiet screen is not a disconnected reader. Readers retry below;
// the server watchdog handles upstream encoder stalls without a PLI storm.
const offlineOverlay = document.getElementById('offline-overlay');
const OFFLINE_GRACE_SECS = 3;
let _lastFc = -1, _stableSec = 0, _nextPliSec = 0, _nextRestartSec = 0;
setInterval(() => {
    if (batchManaged && !batchSelected) {
        offlineOverlay.classList.add('hidden');
        _lastFc = frameCount; _stableSec = _nextPliSec = _nextRestartSec = 0;
        return;
    }
    if (frameCount !== _lastFc) {
        _stableSec = 0;
        offlineOverlay.classList.add('hidden');
    } else {
        _stableSec++;
        const disconnected = videoConnection.state === 'retrying' &&
            videoConnection.outageMs() >= OFFLINE_GRACE_SECS * 1000;
        offlineOverlay.classList.toggle('hidden', !disconnected);
    }
    _lastFc = frameCount;
}, 1000);

// ----- Collapse recovery is SERVER-side, not here.
// Recovery from the collapse (the device re-emitting a full-res IDR) is driven
// SERVER-side by the motion-triggered decoder-refresh (--motion-idr): it fires
// preemptively the moment motion starts, so it's structurally faster than any
// client-side detect-then-POST-/pli loop (which is always a collapse-cycle
// behind). The viewer's job is just to hide the shrink until that IDR lands,
// which detectContentCrop above does. No client-side keyframe requests here.

// ----- Accessibility panel: GET /accessibility lists current settings,
// POST /accessibility/set with {key, value} updates one, POST
// /accessibility/reset wipes everything back to defaults. Values can
// be bool (checkbox) or float (slider 0..1) -- the device's
// DYNAMIC_TYPE setting is a float; everything else we've observed is
// a bool.
const axList = document.getElementById('accessibility-list');
const AX_ZH = {"ui_style": "外观", "text_size": "文字大小", "color_filter": "色彩滤镜", "reduce_motion": "减弱动态效果", "show_borders": "显示按钮边框", "reduce_transparency": "降低透明度", "increase_contrast": "增强对比度", "liquid_glass_opacity": "液态玻璃不透明度", "extraSmall": "特小", "small": "小", "medium": "中", "large": "大", "extraLarge": "特大", "extraExtraLarge": "超大", "extraExtraExtraLarge": "最大", "accessibilityMedium": "辅助：中", "accessibilityLarge": "辅助：大", "accessibilityExtraLarge": "辅助：特大", "accessibilityExtraExtraLarge": "辅助：超大", "accessibilityExtraExtraExtraLarge": "辅助：最大"};
function renderAxRow(setting) {
    const row = document.createElement('div');
    row.className = 'axrow';
    const id = 'ax-' + setting.key;
    const label = document.createElement('label');
    label.setAttribute('for', id);
    label.textContent = AX_ZH[setting.key] || setting.key.replace(/_/g, ' ').toLowerCase();
    label.title = AX_ZH[setting.key] || setting.key;
    row.appendChild(label);
    const type = setting.type || (typeof setting.value === 'boolean' ? 'bool' : 'float');
    if (type === 'bool') {
        const cb = document.createElement('input');
        cb.type = 'checkbox'; cb.id = id; cb.checked = !!setting.value;
        cb.addEventListener('change', () => postAxSet(setting.key, cb.checked));
        row.appendChild(cb);
    } else if (type === 'enum') {
        const sel = document.createElement('select');
        sel.id = id;
        for (const opt of (setting.options || [])) {
            const o = document.createElement('option');
            o.value = opt; o.textContent = AX_ZH[opt] || ({light:'浅色',dark:'深色',automatic:'自动'})[opt] || opt;
            if (opt === setting.value) o.selected = true;
            sel.appendChild(o);
        }
        sel.addEventListener('change', () => postAxSet(setting.key, sel.value));
        row.appendChild(sel);
    } else {
        const sl = document.createElement('input');
        sl.type = 'range'; sl.id = id; sl.min = '0'; sl.max = '1'; sl.step = '0.05';
        sl.value = String(setting.value);
        const v = document.createElement('span');
        v.className = 'axvalue'; v.textContent = Number(setting.value).toFixed(2);
        sl.addEventListener('input', () => { v.textContent = Number(sl.value).toFixed(2); });
        sl.addEventListener('change', () => postAxSet(setting.key, Number(sl.value)));
        row.appendChild(sl); row.appendChild(v);
    }
    return row;
}
async function reloadAccessibility() {
    try {
        const r = await fetch('/accessibility', { cache: 'no-store' });
        if (!r.ok) { axList.textContent = '读取失败：HTTP ' + r.status; return; }
        const j = await r.json();
        axList.innerHTML = '';
        for (const s of j.settings || []) axList.appendChild(renderAxRow(s));
    } catch (e) { axList.textContent = '读取失败：' + (e.message || e); }
}
async function postAxSet(key, value) {
    try {
        const r = await fetch('/accessibility/set', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({key, value}),
        });
        if (!r.ok) log('ax set ' + key + ': HTTP ' + r.status);
        else log('ax: ' + key + ' = ' + value);
    } catch (e) { log('ax set err: ' + (e.message || e)); }
}
document.getElementById('accessibility-reset').addEventListener('click', async () => {
    try {
        const r = await fetch('/accessibility/reset', {method: 'POST'});
        if (!r.ok) { log('ax reset HTTP ' + r.status); return; }
        log('accessibility reset');
        reloadAccessibility();
    } catch (e) { log('ax reset err: ' + (e.message || e)); }
});
reloadAccessibility();

// ----- Clipboard panel: bridge to the device pasteboard (text and images).
// "Send to device" pushes the textarea contents via POST /clipboard.
// "Get from device" pulls via GET /clipboard (+ /clipboard/image), shows
// it in the panel, and (on a secure context) also puts it on the browser
// clipboard so the user can paste directly into a host app. The header
// toggle ("on"/"off") gates the whole panel.
const clipboardTextEl = document.getElementById('clipboard-text');
const clipboardImageEl = document.getElementById('clipboard-image');
const clipboardPanel = document.getElementById('clipboard-panel');
const clipboardSendBtn = document.getElementById('clipboard-send');
const clipboardGetBtn = document.getElementById('clipboard-get');
const clipboardToggleBtn = document.getElementById('clipboard-toggle');
let clipboardEnabled = true;
clipboardToggleBtn.classList.add('active');
function setClipboardEnabled(on) {
    clipboardEnabled = on;
    clipboardToggleBtn.textContent = on ? '开启' : '关闭';
    clipboardToggleBtn.classList.toggle('active', on);
    clipboardPanel.classList.toggle('disabled', !on);
}
clipboardToggleBtn.addEventListener('click', () => setClipboardEnabled(!clipboardEnabled));

// Clipboard content travels as {text: string|null, image: Blob|null}.
// fingerprint() identifies it so content that just crossed the bridge isn't
// bounced straight back to where it came from.
async function fingerprint(content) {
    if (content.image) {
        const digest = await crypto.subtle.digest('SHA-1', await content.image.arrayBuffer());
        return 'image:' + [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
    }
    return content.text ? 'text:' + content.text : null;
}
function describe(content) {
    return content.image ? 'image, ' + Math.round(content.image.size / 1024) + ' KB' : content.text.length + ' chars';
}

// The browser clipboard only takes PNG. The device hands out whatever the
// copying app put there (JPEG from Photos, ...), so re-encode through a canvas.
async function toPng(blob) {
    if (blob.type === 'image/png') return blob;
    const bitmap = await createImageBitmap(blob);
    const c = document.createElement('canvas');
    c.width = bitmap.width; c.height = bitmap.height;
    c.getContext('2d').drawImage(bitmap, 0, 0);
    bitmap.close();
    return new Promise((resolve, reject) => c.toBlob(b => b ? resolve(b) : reject(new Error('PNG encode failed')), 'image/png'));
}

function showInPanel(content) {
    clipboardTextEl.value = content.text || '';
    if (clipboardImageEl.src) URL.revokeObjectURL(clipboardImageEl.src);
    clipboardImageEl.classList.toggle('hidden', !content.image);
    if (content.image) clipboardImageEl.src = URL.createObjectURL(content.image);
    else clipboardImageEl.removeAttribute('src');
}

async function readHostClipboard() {
    const native = await fetch('/host-clipboard', {cache:'no-store', signal: AbortSignal.timeout(5000)});
    if (native.ok) {
        const value = await native.json();
        const image = value.image_png
            ? new Blob([Uint8Array.from(atob(value.image_png), c => c.charCodeAt(0))], {type: 'image/png'}) : null;
        return {text: value.text, image};
    }
    if (native.status === 403) throw new Error('当前手机未获得控制权限');
    if (!navigator.clipboard) throw new Error('电脑剪贴板暂不可用');
    const content = {text: null, image: null};
    if (navigator.clipboard.read) {
        for (const item of await navigator.clipboard.read()) {
            if (!content.image && item.types.includes('image/png')) content.image = await item.getType('image/png');
            if (content.text === null && item.types.includes('text/plain')) {
                content.text = await (await item.getType('text/plain')).text();
            }
        }
    } else {
        content.text = await navigator.clipboard.readText();
    }
    return content;
}

// Returns true when the content reached the browser clipboard. Browsers
// refuse clipboard writes from a background document; the caller keeps
// the content and retries on focus.
async function writeHostClipboard(content) {
    if (!batchActive) return false;
    showInPanel(content);
    if (!content.image && typeof content.text === 'string') {
        try {
            const r = await fetch('/host-clipboard', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({text:content.text})
            });
            if (r.ok) { clipboardResult('已复制到电脑，可切换到其他应用粘贴'); return true; }
        } catch (e) {}
    }
    try {
        if (!navigator.clipboard) throw new Error('浏览器不支持剪贴板');
        if (content.image) {
            const parts = {'image/png': await toPng(content.image)};
            if (content.text) parts['text/plain'] = new Blob([content.text], {type:'text/plain'});
            await navigator.clipboard.write([new ClipboardItem(parts)]);
            try { lastShared = await fingerprint(await readHostClipboard()); } catch (e) {}
        } else {
            await navigator.clipboard.writeText(content.text || '');
        }
        clipboardResult('已复制到电脑，可切换到其他应用粘贴');
        return true;
    } catch (e) {
        clipboardResult('已读取手机内容，但未写入电脑。请点“复制到电脑”重试，或选中文字按 Ctrl+C');
        return false;
    }
}

async function fetchDeviceContent(j) {
    const content = {text: j.text == null ? null : String(j.text), image: null};
    if (j.image) {
        const r = await fetch('/clipboard/image?seq=' + (j.seq || Date.now()), {cache: 'no-store'});
        if (r.ok) content.image = await r.blob();
    }
    return content;
}

clipboardSendBtn.addEventListener('click', async () => {
    if (!clipboardEnabled || !batchActive) return;
    const text = clipboardTextEl.value;
    try {
        const r = await fetch('/clipboard', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text}),
        });
        if (!r.ok) { log('clipboard send: HTTP ' + r.status); return; }
        clipboardResult('已复制到手机，可在手机粘贴');
        log('已发送到手机 (' + text.length + ' 字)');
    } catch (e) { log('发送到手机失败：' + (e.message || e)); }
});

clipboardGetBtn.addEventListener('click', async () => {
    if (!clipboardEnabled || !batchActive) return;
    try {
        const r = await fetch('/clipboard', {cache: 'no-store'});
        if (!r.ok) { log('clipboard get: HTTP ' + r.status); return; }
        const content = await fetchDeviceContent(await r.json());
        if (!content.text && !content.image) { showInPanel(content); clipboardResult('手机剪贴板为空，请先在手机上复制文字'); return; }
        lastShared = await fingerprint(content);
        // Best-effort push to the browser clipboard: needs a secure context
        // (https:// or localhost) and a user gesture, which the click is.
        // The content is in the panel either way.
        const written = await writeHostClipboard(content);
        pendingHostWrite = written ? null : content;
        log('clipboard from device (' + describe(content) + (written ? ', also in browser clipboard)' : ')'));
    } catch (e) { log('读取手机剪贴板失败：' + (e.message || e)); }
});

// ----- Shared clipboard ("Sync" toggle). Device -> host: long-poll
// /clipboard/events (the server holds the request until something is copied
// on the device) and write it into the browser clipboard. Host -> device:
// read the browser clipboard whenever this page regains focus and right
// before a paste shortcut is forwarded, and POST it when it changed. Both
// directions need navigator.clipboard, i.e. a secure context (localhost or
// --https); without it device copies still show up in the panel.
const clipboardResultEl = document.getElementById('clipboard-result');
function clipboardResult(message) { clipboardResultEl.textContent = message; }
document.getElementById('clipboard-copy').addEventListener('click', async () => {
    if (!clipboardEnabled) { clipboardResult('请先开启剪贴板面板'); return; }
    const content = pendingHostWrite || {text:clipboardTextEl.value, image:null};
    if (!content.text && !content.image) { clipboardResult('面板为空，请先点“从手机获取”'); return; }
    if (await writeHostClipboard(content)) pendingHostWrite = null;
});
const clipboardSyncBtn = document.getElementById('clipboard-sync');
let clipboardSync = false;
let clipboardSyncAbort = null;
let lastShared = null;        // fingerprint() of the last content that crossed the bridge
// Device copy that couldn't be written because the page wasn't focused.
let pendingHostWrite = null;

async function pushHostClipboard() {
    if (!clipboardSync || !batchActive) return;
    let content, mark;
    try {
        content = await readHostClipboard();
        mark = await fingerprint(content);
    } catch (e) { return; }
    if (!mark || mark === lastShared) return;
    // Claimed up front so a focus and a paste shortcut racing each other send
    // it once; given back when it didn't get through, or the next focus would
    // take it for already shared and never retry.
    lastShared = mark;
    const unclaim = () => { if (lastShared === mark) lastShared = null; };
    try {
        const r = content.image
            ? await fetch('/clipboard/image', {method: 'POST', headers: {'Content-Type': 'image/png'}, body: content.image})
            : await fetch('/clipboard', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: content.text}),
            });
        if (!r.ok) { unclaim(); log('clipboard sync: HTTP ' + r.status); return; }
        showInPanel(content);
        clipboardResult('已复制到手机，可在手机粘贴');
        log('已同步到手机 (' + describe(content) + ')');
    } catch (e) { unclaim(); log('剪贴板同步失败：' + (e.message || e)); }
}

async function clipboardSyncLoop(signal) {
    let since = null;
    while (!signal.aborted && batchActive) {
        try {
            const url = '/clipboard/events' + (since === null ? '' : '?since=' + since);
            const r = await fetch(url, {cache: 'no-store', signal});
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const j = await r.json();
            since = j.seq;
            if (j.text == null && !j.image) continue;
            const content = await fetchDeviceContent(j);
            const mark = await fingerprint(content);
            if (!mark) continue;
            // Not compared with lastShared: the server already drops the echo
            // of what the host sent, and the host clipboard may have changed
            // since without this page seeing it, so a repeat is a real copy.
            lastShared = mark;
            const written = await writeHostClipboard(content);
            pendingHostWrite = written ? null : content;
            log('clipboard sync from device (' + describe(content) +
                (written ? ')' : ', lands in the clipboard when this page is focused)'));
        } catch (e) {
            if (signal.aborted) return;
            log('剪贴板同步失败：' + (e.message || e));
            await new Promise(r => setTimeout(r, 2000));
        }
    }
}

function setClipboardSync(on) {
    clipboardSync = on;
    clipboardSyncBtn.textContent = '双向同步：' + (on ? '开启' : '关闭');
    clipboardSyncBtn.classList.toggle('active', on);
    try { localStorage.setItem('clipboardSync', on ? 'true' : 'false'); } catch (e) {}
    if (clipboardSyncAbort) { clipboardSyncAbort.abort(); clipboardSyncAbort = null; }
    if (!on) { pendingHostWrite = null; return; }
    if (!navigator.clipboard) {
        log('文本使用 Windows 系统剪贴板；图片需要浏览器剪贴板权限');
    }
    if (!batchActive) return;
    clipboardSyncAbort = new AbortController();
    clipboardSyncLoop(clipboardSyncAbort.signal);
    clipboardResult(on ? '双向同步已开启：在手机复制新文字，或在电脑复制后点击本页再粘贴到手机' : '双向同步已关闭');
}
clipboardSyncBtn.addEventListener('click', () => setClipboardSync(!clipboardSync));
window.addEventListener('focus', async () => {
    if (!clipboardSync || !batchActive) return;
    if (pendingHostWrite === null) { pushHostClipboard(); return; }
    if (await writeHostClipboard(pendingHostWrite)) pendingHostWrite = null;
});
try { if (!batchManaged && localStorage.getItem('clipboardSync') === 'true') setClipboardSync(true); } catch (e) {}

async function readCompatibleFrames(reader, onFrame, decodeImage = createImageBitmap) {
    let buffer = new Uint8Array(0), latestImage = null, decodeTask = null;
    let running = true, failure = null;
    async function decodeLatest() {
        while (running && latestImage) {
            const image = latestImage;
            latestImage = null;
            const frame = await decodeImage(new Blob([image], {type: 'image/jpeg'}));
            if (!running) { frame.close(); return; }
            onFrame(frame);
        }
    }
    function startDecode() {
        if (!latestImage || decodeTask) return;
        decodeTask = decodeLatest().catch(error => {
            failure = error;
            return reader.cancel().catch(() => {});
        }).finally(() => {
            decodeTask = null;
            if (running && !failure) startDecode();
        });
    }
    try {
        while (true) {
            const {value, done} = await reader.read();
            if (failure) throw failure;
            if (done) throw Error('视频连接已断开');
            videoDiagnostics.receivedAt = performance.now(); videoDiagnostics.packets++;
            const merged = new Uint8Array(buffer.length + value.length);
            merged.set(buffer); merged.set(value, buffer.length); buffer = merged;
            while (buffer.length >= 4) {
                const size = new DataView(buffer.buffer, buffer.byteOffset, 4).getUint32(0);
                if (!size || size > 8 * 1024 * 1024) throw Error('视频帧格式无效');
                if (buffer.length < size + 4) break;
                latestImage = buffer.slice(4, size + 4); buffer = buffer.subarray(size + 4);
            }
            // Keep draining the network while a bitmap decodes. Retain only
            // one waiting JPEG, so slow decoding cannot queue seconds of video.
            startDecode();
        }
    } finally {
        running = false;
        latestImage = null;
        if (decodeTask) await decodeTask;
    }
}

async function runCompatibleVideo() {
    videoDiagnostics.mode='jpeg';videoDiagnostics.decoderState='jpeg';
    log('使用兼容视频解码');
    while (!videoStopped) {
        while (!videoStopped && batchManaged && !batchVisible) await new Promise(resolve => setTimeout(resolve, 50));
        if (videoStopped) return;
        compatibleVideoAbort = new AbortController();
        try {
            const response = await fetch('/jpeg.bin', {cache: 'no-store', signal: compatibleVideoAbort.signal});
            if (!response.ok) throw Error('视频服务暂不可用');
            videoConnection.connected();
            const reader = response.body.getReader();
            try {
                await readCompatibleFrames(reader, frame => {
                    Object.defineProperties(frame, {displayWidth: {value: frame.width}, displayHeight: {value: frame.height}});
                    queueVideoFrame(frame);
                });
            } finally { await reader.cancel().catch(() => {}); }
        } catch (error) {
            videoDiagnostics.record('jpeg-reader-disconnected');
            videoConnection.disconnected();
            if (error.name !== 'AbortError') log('兼容视频：' + error.message + '，正在重连');
        }
        videoConnection.disconnected();
        compatibleVideoAbort = null;
        await videoConnection.waitRetry();
    }
}

function waitForDecoderDrain(decoder,signal,limit=6,timeout=250){
    if(decoder.decodeQueueSize<limit)return Promise.resolve(true);
    return new Promise(resolve=>{
        let done=false,timer=null;
        const finish=result=>{
            if(done)return;done=true;
            if(timer!==null)clearTimeout(timer);
            decoder.removeEventListener?.('dequeue',changed);
            signal?.removeEventListener('abort',aborted);
            resolve(result);
        };
        const changed=()=>{
            if(decoder.state!=='configured')finish(false);
            else if(decoder.decodeQueueSize<limit)finish(true);
        };
        const aborted=()=>finish(false);
        decoder.addEventListener?.('dequeue',changed);
        signal?.addEventListener('abort',aborted,{once:true});
        timer=setTimeout(()=>finish(decoder.state==='configured'&&decoder.decodeQueueSize<limit),timeout);
        if(signal?.aborted)aborted();else changed();
    });
}
async function run() {
    videoDiagnostics.mode='hevc';
    nativeVideoAbort = new AbortController();
    log('userAgent: ' + navigator.userAgent.slice(0, 80));
    const { codec, description } = await fetchCodecWithRetry();
    if (videoStopped) return;
    log('codec: ' + codec + ' (hvcC ' + description.length + 'B)');
    // Shared hvcC decoder config: the `description` (HEVCDecoderConfigurationRecord)
    // selects VideoToolbox's native hvcC path; chunks carry 4-byte-length-prefixed
    // NALUs (the /stream.bin framing) rather than Annex-B start codes.
    const decoderConfig = { codec, description, optimizeForLatency: true };

    let support;
    try {
        support = await VideoDecoder.isConfigSupported({ codec, description });
    } catch (e) {
        log('isConfigSupported threw: ' + e.message); return runCompatibleVideo();
    }
    log('isConfigSupported: ' + JSON.stringify(support));
    if (!support.supported) { log('浏览器不支持 HEVC，切换兼容视频'); return runCompatibleVideo(); }

    let decodeErrCount = 0;
    let needsResync = false;     // skip deltas until we see the next key after an error
    let waitingSince = null, keyRequests = 0, nextKeyRequestAt = 0;
    let ended = false, recoveryTimer = null;
    const now = () => performance.now();
    const requestKey = () => {
        if (ended || keyRequests >= 3 || now() < nextKeyRequestAt) return;
        keyRequests++;
        nextKeyRequestAt = now() + 2000 * 2 ** (keyRequests - 1);
        videoDiagnostics.record('browser-pli');
        fetch('/pli', {method: 'POST', cache: 'no-store', signal: AbortSignal.timeout(4000)})
            .catch(() => videoDiagnostics.record('browser-pli-failed'));
    };
    const resync = reason => {
        if (needsResync || ended) return;
        needsResync = true;
        waitingSince = now(); videoDiagnostics.keyWaitAt = waitingSince;
        keyRequests = 0; nextKeyRequestAt = 0;
        videoDiagnostics.record(reason);
        requestKey();
    };
    let decoderEpoch = 0;
    const buildDecoder = () => {
        const epoch = ++decoderEpoch;
        return new VideoDecoder({
        output: (frame) => {
            if (ended || needsResync || epoch !== decoderEpoch) { frame.close(); return; }
            // Apple's encoder signals slightly different displayWidth/Height
            // across frames (we've measured 1264x2752 oscillating with
            // 1264x2736 mid-stream as the iOS home indicator toggles). If
            // we resize the canvas on every change the entire <canvas>
            // visibly shrinks/expands -- that's the "screen changing size"
            // pattern the user sees. Lock the canvas to the largest size
            // we've seen so frames just draw into the existing surface.
            // Resize the canvas buffer to match each frame's exact
            // dimensions. We used to lock the canvas to the largest size
            // ever seen (to keep the page layout from jittering when iOS
            // toggles the home-indicator between 2752/2736 pixels mid-
            // stream), but that left the canvas buffer at max-ever size
            // forever -- and even with drawImage-stretch fillout, the
            // browser still carries stale GPU-side state from prior
            // frames that shows up as torn strips during motion.
            // Reassigning canvas.width/.height resets the entire buffer
            // and reattaches a fresh GPU texture, mirroring what a full
            // page reload does. Page layout stability comes from the
            // canvas CSS (max-width/max-height + aspect-ratio if you want
            // to lock that explicitly).
            // Don't drawImage straight from this callback — that runs at
            // the decoder's output cadence (typically irregular: 0..multiple
            // frames per ms during bursts) and races the compositor's
            // vsync read, which is what gets seen as visible horizontal
            // tear bands during quick-swipe motion. Instead, replace the
            // pending frame slot and let requestAnimationFrame draw the
            // latest one in lockstep with the display refresh. Released
            // frames must be .close()'d to free GPU resources.
            queueVideoFrame(frame);
        },
        // Decoder errors propagate asynchronously via this callback. After one,
        // the decoder transitions to 'closed' -- we re-create it and wait for
        // the next keyframe before feeding it again.
        error: (e) => {
            if (ended || epoch !== decoderEpoch) return;
            decodeErrCount++;
            log('decode err #' + decodeErrCount + ': ' + e.message);
            resync('async-decode-error');
        },
        });
    };
    let decoder = buildDecoder();
    try{decoder.configure(decoderConfig);}catch(error){try{decoder.close();}catch{}throw error;}
    log('state after configure: ' + decoder.state);

    // /stream.bin can return 503 if the force-restart on the server failed
    // (e.g. RemoteXPC handshake stuck) -- retry with backoff so a flaky
    // device daemon doesn't leave the viewer permanently dead.
    let resp = null;
    const streamDelays = [200, 500, 1000, 2000, 3000, 5000];
    for (let a = 0; a <= streamDelays.length; a++) {
        if (videoStopped) { decoder.close(); return; }
        if (a > 0) {
            log('stream retry #' + a + ' in ' + streamDelays[a - 1] + 'ms');
            await new Promise(r => setTimeout(r, streamDelays[a - 1]));
        }
        try {
            const r = await fetch('/stream.bin', { cache: 'no-store', signal: nativeVideoAbort.signal });
            if (r.ok) { resp = r; break; }
            const body = await r.text();
            log('stream HTTP ' + r.status + ': ' + body.slice(0, 80));
        } catch (e) {
            log('stream fetch err: ' + (e.message || e));
        }
    }
    if (!resp) { decoder.close(); log('FAIL: /stream.bin unreachable'); return; }
    videoConnection.connected();
    const reader = resp.body.getReader();
    recoveryTimer = setInterval(() => {
        videoDiagnostics.queue = decoder.decodeQueueSize;
        videoDiagnostics.decoderState=decoder.state;
        if (!needsResync) return;
        if (now() - waitingSince >= 15000) {
            videoDiagnostics.record('key-wait-timeout');
            nativeVideoAbort?.abort();
            reader.cancel().catch(() => {});
        } else requestKey();
    }, 500);
    let buf = new Uint8Array(0);
    let timestamp = 0;
    let gotKey = false;
    let sentCount = 0;
    try {
    while (true) {
        const { value, done } = await reader.read();
        if (done) { videoDiagnostics.record('reader-eof'); log('stream ended'); break; }
        videoDiagnostics.receivedAt = now();
        const merged = new Uint8Array(buf.length + value.length);
        merged.set(buf); merged.set(value, buf.length);
        buf = merged;
        while (buf.length >= 4) {
            const len = new DataView(buf.buffer, buf.byteOffset, 4).getUint32(0);
            if (len < 2 || len > 8 * 1024 * 1024) throw Error('Invalid video packet length');
            if (buf.length < 4 + len) break;
            const type = buf[4];
            if (type > 2) throw Error('Invalid video packet type');
            videoDiagnostics.packets++;
            const data = buf.slice(5, 4 + len);  // .slice copies the backing buffer
            buf = buf.subarray(4 + len);
            // type:
            //   0 = key (IDR) -- decode normally
            //   1 = delta
            //   2 = key WITH RESET -- server detected an upstream drop; the
            //       decoder's reference state may be silently stale, so
            //       rebuild before decoding this IDR. (VideoToolbox often
            //       renders torn frames without firing the error callback.)
            if (type === 2) {
                try { decoder.close(); } catch (e) {}
                decoder = buildDecoder();
                decoder.configure(decoderConfig);
                needsResync = false;
                videoDiagnostics.keyWaitAt = waitingSince = null;
                gotKey = true;
                log('force-restart @ key after upstream drop');
            } else if (type === 0) {
                gotKey = true;
                if (needsResync) {
                    try { decoder.close(); } catch (e) {}
                    decoder = buildDecoder();
                    decoder.configure(decoderConfig);
                    needsResync = false;
                    videoDiagnostics.keyWaitAt = waitingSince = null;
                    log('resynced @ key after ' + decodeErrCount + ' decode err(s)');
                }
            }
            if (!gotKey) continue;
            if (needsResync) continue;
            if (decoder.state !== 'configured') {
                if (type === 0 || type === 2) {
                    try { decoder.close(); } catch (_) {}
                    decoder = buildDecoder(); decoder.configure(decoderConfig);
                } else {
                    resync('decoder-not-configured');
                    continue;
                }
            }
            // Prefer current video over playing a backlog. HEVC deltas depend
            // on earlier frames: reset and wait for a fresh key, never drop an
            // arbitrary delta and then continue using its dependent frames.
            // Network reads can contain a healthy burst. Give decoder tasks a
            // display interval to drain before treating the burst as overload.
            // Apply backpressure without losing reference frames. A 16ms
            // scheduling delay is normal; require 250ms without draining.
            if(decoder.decodeQueueSize>=6)await waitForDecoderDrain(decoder,nativeVideoAbort?.signal);
            if(nativeVideoAbort?.signal.aborted)throw Object.assign(Error('video reader cancelled'),{name:'AbortError'});
            if (needsResync) continue;
            if (decoder.decodeQueueSize >= 6) {
                try { decoder.close(); } catch (e) {}
                if (pendingFrame) { pendingFrame.close(); pendingFrame = null; }
                if (type === 0 || type === 2) {
                    // A recovery key is already available: use it now.
                    decoder = buildDecoder(); decoder.configure(decoderConfig);
                    videoDiagnostics.record('decode-queue-reset-at-key');
                } else {
                    resync('decode-queue-timeout');
                    log('解码积压，等待新关键帧');
                    continue;
                }
            }
            try {
                decoder.decode(new EncodedVideoChunk({
                    type: (type === 0 || type === 2) ? 'key' : 'delta',
                    timestamp: timestamp,
                    data: data,
                }));
                timestamp += 16666;
                videoDiagnostics.submittedAt = now();
                videoDiagnostics.submitted++;
                sentCount++;
            } catch (e) {
                log('sync decode err @' + sentCount + ': ' + e.message);
                resync('sync-decode-error');
            }
        }
    }
    } finally {
        ended = true;
        clearInterval(recoveryTimer);
        videoDiagnostics.queue = 0; videoDiagnostics.keyWaitAt = null;
        try { decoder.close(); } catch (_) {}
        // A fetch reader's cancellation can itself remain pending while a
        // page is frozen. Abort transport and do not block the retry loop on it.
        nativeVideoAbort?.abort();
        try { reader.cancel().catch(()=>{}); } catch (_) {}
    }
}
async function runVideoForever() {
    while (!videoStopped) {
        try { await run(); }
        catch (error) { log('视频连接：' + (error.message || error) + '，正在重连'); }
        videoConnection.disconnected();
        videoDiagnostics.record('reader-retry');
        if (videoStopped) return;
        await videoConnection.waitRetry();
    }
}
function ensureVideoSession(){
    if(videoStopped||videoSessionTask)return;
    videoSessionTask=runVideoForever().catch(error=>log('fatal: '+error.message)).finally(()=>{
        videoSessionTask=null;
        if(!videoStopped)setTimeout(ensureVideoSession,1000);
    });
}
window.addEventListener('pagehide', () => {
    videoStopped = true;
    nativeVideoAbort?.abort(); compatibleVideoAbort?.abort();
    videoConnection.promote(); cancelFrameDraw();
    if (pendingFrame) { pendingFrame.close(); pendingFrame = null; }
    if (lastFrame) { lastFrame.close(); lastFrame = null; }
});
window.addEventListener('pageshow',event=>{
    if(!event.persisted)return;
    videoStopped=false;
    videoDiagnostics.record('page-restored');
    videoConnection.promote();startVideoReports();ensureVideoSession();resumeVideoDraw();
});
inputMonitor = new InputHealthMonitor({
    request: async () => {
        const response = await fetch('/input-health', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: '{}', signal: AbortSignal.timeout(30000)});
        if (!response.ok) throw Error('控制连接检查失败（HTTP ' + response.status + '）');
        return response.json();
    },
    eligible: () => !inputHealthPaused && !pastePending && !document.hidden && activePointer === null &&
        !pointerInput.running && !wheelInput.active && pressedUsages.size === 0,
    changed: state => {
        if (!state.ready && inputReady) inputEpoch++;
        inputReady = state.ready;
        if (!state.ready) { pressedUsages.clear(); windowsEditKeys.clear(); }
        if (state.state === 'unavailable') log('控制连接不可用；可点击设备列表刷新重试');
        if (state.state === 'ready' && state.recovered) log('控制连接已自动恢复');
        if (batchManaged) parent.postMessage({type: 'input-health-result', ...state},
            new URLSearchParams(location.search).get('manager') || 'http://127.0.0.1:8070');
    },
});
if (!batchManaged) inputMonitor.setActive(true);
ensureVideoSession();

if (batchManaged) {
    let snapshotBusy = false, lastSnapshotAt = -Infinity;
    window.addEventListener('message', event => {
        if (event.source !== parent || event.origin !== (new URLSearchParams(location.search).get('manager') || 'http://127.0.0.1:8070')) return;
        if (event.data?.type === 'monitor-snapshot') {
            if (snapshotBusy || typeof event.data.id !== 'string' || event.data.id.length > 80 || performance.now() - lastSnapshotAt < 1400) return;
            if (!pendingFrame && !lastFrame) return;
            // Reuse the warm decoder and present its newest frame; no new stream.
            if (pendingFrame) { cancelFrameDraw(); drawPending(true); }
            if (!canvas.width || !canvas.height) return;
            const thumbnail = document.createElement('canvas');
            const ratio = Math.min(1, 240 / canvas.width, 520 / canvas.height);
            thumbnail.width = Math.max(1, Math.round(canvas.width * ratio));
            thumbnail.height = Math.max(1, Math.round(canvas.height * ratio));
            thumbnail.getContext('2d').drawImage(canvas, 0, 0, thumbnail.width, thumbnail.height);
            snapshotBusy = true; lastSnapshotAt = performance.now();
            thumbnail.toBlob(image => {
                snapshotBusy = false;
                if (image) parent.postMessage({type:'monitor-snapshot-result',id:event.data.id,image,state:videoConnection.state},event.origin);
            }, 'image/jpeg', .65);
            return;
        }
        if (event.data?.type === 'input-recover') {
            if (batchActive) inputMonitor.check(true);
            return;
        }
        if (event.data?.type === 'device-screenshot') {
            const id = event.data.id;
            if (!batchSelected || typeof id !== 'string' || id.length > 80) return;
            fetch('/device-screenshot', {cache:'no-store', signal:AbortSignal.timeout(14000)})
                .then(async response => {
                    const result = await response.json();
                    if (!response.ok) throw Error(result.error || '手机截图失败');
                    parent.postMessage({type:'device-screenshot-result',id,...result},event.origin);
                })
                .catch(() => parent.postMessage({type:'device-screenshot-result',id,error:'手机截图失败，请确认截图服务已加载、设备连接正常后重试'},event.origin));
            return;
        }
        if (event.data?.type === 'paste-composer') {
            const id = event.data.id;
            const respond = (ok, error) => parent.postMessage({type: 'paste-composer-result', id, ok, error}, event.origin);
            if (!controlAvailable() || typeof event.data.text !== 'string' || !event.data.text.trim()) {
                respond(false, '手机控制连接不可用或正文为空'); return;
            }
            canvas.focus({preventScroll: true});
            queueHostPaste(event.data.text).then(() => respond(true), error => respond(false, error.message));
            return;
        }
        if (event.data?.type === 'device-home') {
            if (!controlAvailable()) return;
            releaseActive();
            pointerInput.idle().then(() => fetch('/manual-home', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}', signal: AbortSignal.timeout(5000)}))
                .then(response => {if (!response.ok) throw Error('返回手机主页失败'); parent.postMessage({type: 'device-home-result', ok: true}, event.origin);})
                .catch(error => {inputMonitor.invalidate(); parent.postMessage({type: 'device-home-result', ok: false, error: error.message}, event.origin);});
            return;
        }
        if (event.data?.type !== 'device-focus') return;
        if(event.data.selected!==true||event.data.active!==true)foregroundTapRevision++;
        if (!event.data.active) releaseActive();
        batchActive = event.data.active === true;
        inputHealthPaused = event.data.working === true;
        inputMonitor.setActive(batchActive, event.data.controlReady === true);
        batchVisible = typeof event.data.visible === 'boolean' ? event.data.visible : batchActive;
        setBatchVideoSelected(event.data.selected === true);
        if (!batchVisible && compatibleVideoAbort) compatibleVideoAbort.abort();
        // The dashboard owns the controls; keep its embedded viewer screen-only.
        document.body.classList.add('batch-preview');
        releaseAllKeys();
        pendingHostWrite = null;
        if (clipboardSyncAbort) { clipboardSyncAbort.abort(); clipboardSyncAbort = null; }
        if (batchActive && clipboardSync) setClipboardSync(true);
        updateKbIndicator();
    });
}



