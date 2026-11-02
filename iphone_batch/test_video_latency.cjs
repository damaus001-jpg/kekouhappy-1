const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'web/viewer.js'), 'utf8');
const ticks = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
function packet(data) {
    const bytes = new Uint8Array(4 + data.length);
    new DataView(bytes.buffer).setUint32(0, data.length);
    bytes.set(data, 4);
    return bytes;
}

async function compatibleVideo() {
    const context = vm.createContext({Blob});
    vm.runInContext(source.slice(source.indexOf('async function readCompatibleFrames('), source.indexOf('async function runCompatibleVideo(')), context);
    const firstDecode = deferred(), painted = [], decoded = [];
    let streamControl, reads = 0;
    const stream = new ReadableStream({start(c) { streamControl = c; }});
    const realReader = stream.getReader();
    const reader = {async read() { const r = await realReader.read(); reads++; return r; }, cancel: () => realReader.cancel()};
    const task = context.readCompatibleFrames(reader, frame => painted.push(frame.id), async blob => {
        const id = new Uint8Array(await blob.arrayBuffer())[0];
        decoded.push(id);
        if (id === 1) await firstDecode.promise;
        return {id, close() {}};
    });
    const ended = assert.rejects(task, /视频连接已断开/);
    streamControl.enqueue(packet([1]));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(decoded, [1]);
    for (let i = 2; i <= 40; i++) streamControl.enqueue(packet([i]));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(reads, 40, 'network keeps draining while bitmap decode is blocked');
    assert.deepEqual(decoded, [1], 'only one bitmap decode is in flight');
    firstDecode.resolve();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(decoded, [1, 40], 'intermediate JPEGs are replaced by the newest');
    assert.deepEqual(painted, [1, 40]);
    streamControl.close();
    await ended;

    const gate = deferred();
    let controller, closed = 0, published = 0;
    const canceled = new ReadableStream({start(c) { controller = c; }}).getReader();
    const stopping = context.readCompatibleFrames(canceled, () => published++, async () => {
        await gate.promise;
        return {close() { closed++; }};
    });
    const stopped = assert.rejects(stopping, /视频连接已断开/);
    controller.enqueue(packet([1]));
    await ticks();
    await canceled.cancel();
    await ticks();
    gate.resolve();
    await stopped;
    assert.equal(published, 0, 'a disconnected session never paints a late bitmap');
    assert.equal(closed, 1, 'a late bitmap is released');
}

async function nativeVideo(slow) {
    const types = [0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1];
    const all = Buffer.concat(types.map((type, id) => packet([type, id])));
    const decoders = [], requests = [], decoded = [];
    class Decoder {
        static async isConfigSupported() { return {supported: true}; }
        constructor() { this.state = 'unconfigured'; this.decodeQueueSize = 0; decoders.push(this); }
        configure() { this.state = 'configured'; }
        close() { this.state = 'closed'; }
        decode(chunk) {
            decoded.push(chunk.data[0]); this.decodeQueueSize++;
            if (!slow) queueMicrotask(() => this.decodeQueueSize--);
        }
    }
    let read = false;
    const context = vm.createContext({
        VideoDecoder: Decoder, EncodedVideoChunk: class { constructor(data) { Object.assign(this, data); } },
        fetchCodecWithRetry: async () => ({codec: 'hvc1', description: new Uint8Array()}),
        fetch: async url => { requests.push(url); return {ok: true, body: {getReader: () => ({
            read: async () => read ? {done: true} : (read = true, {value: all, done: false})
        })}}; },
        log() {}, frameCount: 10, pendingFrame: null, navigator: {userAgent: 'test'}, setTimeout
    });
    vm.runInContext(source.slice(source.indexOf('async function run()'), source.indexOf('inputMonitor = new InputHealthMonitor(')), context);
    await context.run();
    if (slow) {
        assert.deepEqual(decoded, [0, 1, 2, 3, 4, 5, 9, 10], 'overloaded decoder skips dependent deltas until the next key');
        assert.equal(requests.filter(x => x === '/pli').length, 1, 'one fresh key request per overload');
        assert.equal(decoders[0].state, 'closed', 'queued decoding is released');
    } else {
        assert.equal(decoded.length, types.length, 'healthy decoding retains all frames');
        assert.equal(requests.includes('/pli'), false);
        assert.equal(decoders.length, 1);
    }
}

(async () => {
    await compatibleVideo();
    await nativeVideo(true);
    await nativeVideo(false);
    console.log('Video latency passed: latest JPEG under slow decode, disconnect cleanup, HEVC overload resync and healthy decoding');
})().catch(error => { console.error(error); process.exitCode = 1; });
