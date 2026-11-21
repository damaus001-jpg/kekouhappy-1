const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, 'web/dashboard.js'), 'utf8');
const code = source.slice(source.indexOf("const phoneScreenshotButton="), source.indexOf("phoneHomeButton?.addEventListener('click'"));
function setup(picker) {
  const elements = new Map(), messages = [], downloads = [], writes = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      disabled: false, hidden: true, open: false, dataset: {}, textContent: '',
      addEventListener(type, callback) { this[type] = callback; },
      showModal() { this.open = true; }, close() { this.open = false; this['close']?.(); },
      click() { downloads.push(this.download); }, remove() {},
    });
    return elements.get(id);
  }
  // close() needs to remain callable, so store event handlers separately.
  const dialog = element('phone-screenshot-dialog');
  dialog.addEventListener = (type, callback) => { dialog[type + 'Handler'] = callback; };
  dialog.close = () => { dialog.open = false; dialog.closeHandler?.(); };
  const frame = {contentWindow: {postMessage(data, origin) { messages.push({data, origin}); }}};
  const context = vm.createContext({
    document: {getElementById: element, createElement: () => element('download'), body: {appendChild() {}}},
    window: {showSaveFilePicker: picker}, Blob, Date, Promise,
    URL: {createObjectURL: () => 'blob:test', revokeObjectURL() {}},
    setTimeout: () => 1, clearTimeout() {},
    latest: [{udid: 'one', ready: true}], active: 'one', controlOwner: 'one',
    devicePreview: false, busy: false, workspaceBusy: false, controlPaused: false,
    cards: new Map([['one', {frame, origin: 'http://127.0.0.1:8080'}]]),
    deviceLabel: () => ({number: '01'}),
  });
  vm.runInContext(code, context);
  element('phone-screenshot').click();
  assert.equal(dialog.open, true);
  async function reply(data, overrides = {}) {
    const id = messages.at(-1).data.id;
    await context.finishScreenshot({source: frame.contentWindow, origin: 'http://127.0.0.1:8080', data: {id, ...data}, ...overrides});
  }
  return {context, element, messages, downloads, writes, reply, dialog};
}

(async () => {
  let picked = 0, resolvePicker;
  const writes = [];
  const ui = setup(() => { picked++; return new Promise(resolve => { resolvePicker = resolve; }); });
  ui.context.requestScreenshot('computer');
  assert.equal(picked, 1, 'picker opens during the click');
  assert.equal(ui.messages[0].data.type, 'canvas-screenshot');
  assert.equal(ui.element('screenshot-native').disabled, true, 'avoid duplicate requests');
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=', 'base64');
  const blob = new Blob([png], {type: 'image/png'});
  await ui.reply({type: 'canvas-screenshot-result', image: blob}, {origin: 'http://wrong-host'});
  assert.equal(ui.element('screenshot-native').disabled, true, 'ignore another frame');
  const pending = ui.reply({type: 'canvas-screenshot-result', image: blob});
  resolvePicker({name: 'shot.png', createWritable: async () => ({write: async value => writes.push(value), close: async () => writes.push('closed')})});
  await pending;
  assert.deepEqual(writes, [blob, 'closed']);
  assert.match(ui.element('phone-screenshot-status').textContent, /shot.png/);

  const cancel = setup(() => Promise.reject(Object.assign(new Error('cancel'), {name: 'AbortError'})));
  cancel.context.requestScreenshot('computer');
  await cancel.reply({type: 'canvas-screenshot-result', image: blob});
  assert.equal(cancel.element('phone-screenshot-status').textContent, '已取消保存。');
  assert.equal(cancel.element('screenshot-computer').disabled, false);

  const native = setup();
  native.context.requestScreenshot('native');
  assert.equal(native.messages[0].data.type, 'native-screenshot');
  await native.reply({type: 'native-screenshot-result', ok: true});
  assert.match(native.element('phone-screenshot-status').textContent, /指令已发送/);
  native.context.controlOwner = null;
  native.context.requestScreenshot('native');
  assert.equal(native.messages.length, 1, 'read-only devices cannot trigger native screenshot');

  const fallback = setup();
  fallback.context.requestScreenshot('computer');
  await fallback.reply({type: 'canvas-screenshot-result', image: blob});
  assert.equal(fallback.downloads.length, 1);
  assert.match(fallback.downloads[0], /^设备01_\d{8}_\d{6}\.png$/);
  fallback.element('screenshot-download').click();
  assert.equal(fallback.downloads.length, 2, 'manual download retry is available');

  let rejectedPickerCalls = 0;
  const denied = setup(async () => {
    rejectedPickerCalls++;
    return {name: 'chosen.png', createWritable: async () => { throw Object.assign(new Error('platform denied'), {name: 'NotAllowedError'}); }};
  });
  denied.context.requestScreenshot('computer');
  await denied.reply({type: 'canvas-screenshot-result', image: blob});
  assert.deepEqual(denied.downloads, ['chosen.png'], 'write denial downloads the PNG instead of losing it');
  assert.match(denied.element('phone-screenshot-status').textContent, /直接写入失败/);
  assert.equal(denied.element('screenshot-download').hidden, false);
  denied.context.requestScreenshot('computer');
  await denied.reply({type: 'canvas-screenshot-result', image: blob});
  assert.equal(rejectedPickerCalls, 1, 'avoid creating another empty file after platform denial');
  assert.equal(denied.downloads.length, 2);

  const brokenWrite = setup(async () => ({name: 'full-disk.png', createWritable: async () => ({
    write: async () => { throw new Error('disk full'); }, close: async () => assert.fail('must not close failed write'), abort: async () => {},
  })}));
  brokenWrite.context.requestScreenshot('computer');
  await brokenWrite.reply({type: 'canvas-screenshot-result', image: blob});
  assert.deepEqual(brokenWrite.downloads, ['full-disk.png']);

  const invalid = setup();
  invalid.context.requestScreenshot('computer');
  await invalid.reply({type: 'canvas-screenshot-result', image: new Blob(['not PNG'], {type:'image/png'})});
  assert.equal(invalid.downloads.length, 0);
  assert.match(invalid.element('phone-screenshot-status').textContent, /有效的 PNG/);

  const switched = setup();
  switched.context.requestScreenshot('computer');
  switched.context.active = 'two';
  await switched.reply({type: 'canvas-screenshot-result', image: blob});
  assert.equal(switched.downloads.length, 0, 'do not save a reply after switching devices');
  assert.equal(switched.dialog.open, false);
  console.log('Screenshot UI: save, cancel, platform write denial, write failure, PNG signature, retry, native control and device switching passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
