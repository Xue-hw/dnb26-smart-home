const { build } = require('esbuild');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const path = require('node:path');
(async () => {
  let native = true, fetcher, decodeError = false, nextId = 0;
  const timers = new Map(), created = [], revoked = [];
  const bundle = await build({ entryPoints: [path.resolve(__dirname, '../src/services/mediaImage.ts')], bundle: true, write: false, format: 'cjs',
    plugins: [{ name: 'native', setup(b) {
      b.onResolve({ filter: /^@capacitor\/core$/ }, () => ({ path: 'native', namespace: 'fixture' }));
      b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const Capacitor={isNativePlatform:()=>globalThis.__native()};' }));
    } }],
  });
  const mod = { exports: {} };
  vm.runInNewContext(bundle.outputFiles[0].text, { module: mod, exports: mod.exports, __native: () => native,
    Uint8Array, Blob, DOMException, AbortController,
    fetch: (...args) => fetcher(...args),
    Image: class { naturalWidth = 640; naturalHeight = 480; set src(value) { if (value) queueMicrotask(() => decodeError ? this.onerror?.() : this.onload?.()); } },
    URL: { createObjectURL: () => { const url = 'blob:owned-'+created.length; created.push(url); return url; }, revokeObjectURL: url => revoked.push(url) },
    setTimeout: (fn, delay) => { assert.equal(delay, 15000); const id = ++nextId; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
  });
  const { loadMediaImage } = mod.exports;
  for (const [status, headers, expected] of [[503, {}, /503/], [200, { 'Content-Type': 'text/html' }, /有效图片/], [200, { 'Content-Type': 'image/jpeg', 'Content-Length': '9000000' }, /8 MB/]]) {
    let cancelled = 0;
    fetcher = async () => new Response(new ReadableStream({ cancel() { cancelled++; } }), { status, headers });
    await assert.rejects(loadMediaImage('http://backend/image.jpg'), expected);
    assert.equal(cancelled, 1, 'bad headers must cancel the body, not leave an open download'); assert.equal(timers.size, 0);
  }
  let cancelled = 0;
  fetcher = async () => new Response(new ReadableStream({ start(c) { c.enqueue(new Uint8Array(8*1024*1024+1)); }, cancel() { cancelled++; } }), { headers: { 'Content-Type': 'image/jpeg' } });
  await assert.rejects(loadMediaImage('http://backend/large.jpg'), /8 MB/); assert.equal(cancelled, 1);
  let activeSignal;
  fetcher = async (_, options) => { activeSignal = options.signal; return new Response(new ReadableStream({ start(c) { options.signal.addEventListener('abort', () => c.error(new DOMException('Aborted', 'AbortError')), { once: true }); } }), { headers: { 'Content-Type': 'image/jpeg' } }); };
  const stalled = loadMediaImage('http://backend/stalled.jpg'); const rejected = assert.rejects(stalled, /超时/);
  await new Promise(resolve => setImmediate(resolve)); [...timers.values()].at(-1)(); await rejected;
  assert(activeSignal.aborted); assert.equal(timers.size, 0);
  const caller = new AbortController(); const pending = loadMediaImage('http://backend/cancel.jpg', caller.signal);
  const aborted = assert.rejects(pending, error => error.name === 'AbortError'); caller.abort(); await aborted;
  assert(activeSignal.aborted); assert.equal(timers.size, 0);
  fetcher = async () => new Response(new Uint8Array([255,216,255,217]), { headers: { 'Content-Type': 'image/jpeg' } });
  const loaded = await loadMediaImage('http://backend/ok.jpg'); assert.equal(loaded.image.naturalWidth, 640); loaded.release(); loaded.release();
  decodeError = true; await assert.rejects(loadMediaImage('http://backend/bad.jpg'), /图片读取失败/); decodeError = false;
  assert.deepEqual([...revoked].sort(), [...created].sort());
  fetcher = () => { throw new Error('local and browser images must not fetch'); };
  const local = await loadMediaImage('blob:user-owned'); local.release();
  native = false; const web = await loadMediaImage('http://backend/web.jpg'); web.release();
  assert.equal(timers.size, 0); assert.equal(created.length, 2);
  console.log('PASS: media response/body limits, invalid headers cancel, timeout, external abort, decode failure and URL ownership');
})().catch(error => { console.error(error); process.exit(1); });
