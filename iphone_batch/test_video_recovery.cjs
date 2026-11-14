const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const baseline = process.argv.includes('--baseline-burst');
const source = baseline ? require('node:child_process').execFileSync('git',
    ['-c','safe.directory=C:/xiangmu/qunkong','show','HEAD:iphone_batch/web/viewer.js'],
    {cwd:require('node:path').join(__dirname,'..'),encoding:'utf8'}) :
    fs.readFileSync(require('node:path').join(__dirname, 'web/viewer.js'), 'utf8');
const runSource = source.slice(source.indexOf(baseline?'async function run()':'function waitForDecoderDrain('), source.indexOf('async function runVideoForever()'));
function packet(types) {
    return Buffer.concat(types.map((type, id) => Buffer.from([0, 0, 0, 2, type, id])));
}
async function scenario(mode) {
    let clock = 0, read = false, tick = null, canceled = 0, lateClosed = 0;
    const requests = [], decoded = [], decoders = [], events = [];
    const types = mode === 'burst' ? [0,1,1,1,1,1,1,1,1] :
        mode === 'waiting' ? [0,1,1] : [0,1,1,0,1];
    class Decoder {
        static async isConfigSupported() { return {supported:true}; }
        constructor(callbacks) { this.callbacks = callbacks; this.state='unconfigured'; this.decodeQueueSize=0; this.listeners=new Set();decoders.push(this); }
        addEventListener(name,fn){if(name==='dequeue')this.listeners.add(fn);}
        removeEventListener(name,fn){if(name==='dequeue')this.listeners.delete(fn);}
        configure() {this.state='configured';}
        close() {this.state='closed';}
        decode(chunk) {
            decoded.push(chunk.data[0]);
            if (mode === 'burst') this.decodeQueueSize++;
            else if (chunk.data[0] === 1 && mode!=='cancel-stalled') {
                if (mode === 'sync' || mode === 'waiting') throw Error('simulated');
                this.state='closed'; this.callbacks.error(Error('simulated'));
            }
        }
    }
    const reader = {
        async read() {
            if (!read) {read=true; return {value:packet(types), done:false};}
            if (mode === 'waiting') for (const at of [1000,3000,7000,15001]) {clock=at; tick();}
            return {done:true};
        }, cancel() {canceled++;return mode==='cancel-stalled'?new Promise(()=>{}):Promise.resolve();}
    };
    const context = vm.createContext({VideoDecoder: Decoder, AbortSignal, AbortController, videoStopped:false,
        performance:{now:()=>clock},
        EncodedVideoChunk:class {constructor(data){Object.assign(this,data);}},
        fetchCodecWithRetry:async()=>({codec:'hvc1',description:new Uint8Array()}),
        fetch:async url=>{requests.push(url);return {ok:true,body:{getReader:()=>reader}};},
        setTimeout:(fn,ms)=>{queueMicrotask(()=>{clock+=ms===250?30:ms;if(clock>=30)decoders.forEach(d=>{d.decodeQueueSize=0;for(const listener of d.listeners)listener();});fn();});},clearTimeout(){},
        setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{tick=null;},
        log(){}, navigator:{userAgent:'test'}, pendingFrame:null,
        videoDiagnostics:{packets:0,record:reason=>events.push(reason)},
        videoConnection:{connected(){}}, queueVideoFrame(){throw Error('late output must be closed');}
    });
    vm.runInContext(runSource,context);
    await context.run();
    assert.equal(tick,null,'recovery timer is released');
    assert.ok(decoders.every(d=>d.state==='closed'),'all decoders released on EOF');
    if(!baseline) {
        decoders.at(-1).callbacks.output({close(){lateClosed++;}});
        assert.equal(lateClosed,1,'late output is released without painting');
    }
    assert.ok(!requests.includes('/restart'),'browser never independently restarts source');
    if(mode==='burst') {
        assert.equal(decoders.length,baseline?2:1,'30ms burst rebuild count');
        assert.equal(decoded.length,baseline?6:types.length,'retained reference frames');
        assert.equal(requests.filter(p=>p==='/pli').length,baseline?1:0);
        console.log(JSON.stringify({baseline,scenario:'9 packets; decoder drains at 30ms',
            rebuilds:decoders.length-1,submitted:decoded.length,pli:requests.filter(p=>p==='/pli').length}));
    } else if(mode==='cancel-stalled') {
        assert.equal(decoded.length,types.length,'pending reader.cancel never holds decoder teardown hostage');
    } else if(mode==='waiting') {
        assert.equal(requests.filter(p=>p==='/pli').length,3,'key requests have bounded retries');
        assert.ok(events.includes('key-wait-timeout'));
        assert.ok(canceled>=1,'silent key wait actively cancels reader');
        assert.equal(decoders.length,1,'no speculative rebuild before a key arrives');
    } else {
        assert.deepEqual(decoded,[0,1,3,4],'dependent deltas withheld until a key');
        assert.equal(decoders.length,2,'one rebuild at recovery key');
        assert.equal(requests.filter(p=>p==='/pli').length,1,'sync and async errors both request recovery');
    }
}
(async()=>{for(const mode of (baseline?['burst']:['burst','sync','async','waiting','cancel-stalled']))await scenario(mode);
    console.log(baseline ? 'Baseline burst failure reproduced' :
        'Video recovery passed: 30ms burst, sync/async errors, bounded silent key wait, late frame release');
})().catch(e=>{console.error(e);process.exitCode=1;});
