const { build } = require('esbuild');
const { JSDOM } = require('jsdom');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
async function until(check) { for (let i = 0; i < 80; i++) { if (check()) return; await tick(); } assert(check()); }
const packet = new Uint8Array([...new TextEncoder().encode('--frame\r\nContent-Type: image/jpeg\r\n\r\n'),255,216,1,255,217,...new TextEncoder().encode('\r\n--frame\r\n')]);

(async () => {
  const bundle = await build({ stdin: { contents: `import {StrictMode} from 'react';import {createRoot} from 'react-dom/client';
    import {LiveVideo} from './src/components/LiveVideo';const root=createRoot(document.getElementById('root'));
    const fail=()=>window.__failed++, ready=()=>window.__ready++;
    window.__render=src=>root.render(<StrictMode><LiveVideo src={src} onError={fail} onReady={ready}/></StrictMode>);
    window.__unmount=()=>root.unmount();window.__render('/first');`, resolveDir: root, loader: 'tsx' },
    bundle: true, write: false, format: 'iife', tsconfig: path.join(root, 'tsconfig.json'),
    plugins: [{ name: 'native', setup(b) {
      b.onResolve({ filter: /^@capacitor\/core$/ }, () => ({ path: 'native', namespace: 'fixture' }));
      b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const Capacitor={isNativePlatform:()=>true};' }));
    } }],
  });
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://localhost', runScripts: 'outside-only' });
  const w = dom.window, requests = [], created = [], revoked = [], watchdogs = new Map(); let timer = -1;
  const realTimeout = w.setTimeout.bind(w), realClear = w.clearTimeout.bind(w);
  w.__failed = 0; w.__ready = 0; w.TextEncoder = TextEncoder; w.TextDecoder = TextDecoder;
  w.setTimeout = (callback, delay) => { if (delay !== 10000) return realTimeout(callback, delay); const id = timer--; watchdogs.set(id, callback); return id; };
  w.clearTimeout = id => { if (!watchdogs.delete(id)) realClear(id); };
  w.URL.createObjectURL = () => { const url = 'blob:https://localhost/frame-'+created.length; created.push(url); return url; };
  w.URL.revokeObjectURL = url => revoked.push(url);
  w.Image = class { set src(value) { if (value) queueMicrotask(() => this.onload?.()); } };
  w.fetch = async (url, options) => {
    let controller;
    const stream = new ReadableStream({ start(c) { controller = c; } });
    const request = { url, signal: options.signal, emit() { controller.enqueue(packet); } }; requests.push(request);
    if (options.signal.aborted) controller.error(new DOMException('Aborted', 'AbortError'));
    else options.signal.addEventListener('abort', () => controller.error(new DOMException('Aborted', 'AbortError')), { once: true });
    return new Response(stream, { headers: { 'Content-Type': 'multipart/x-mixed-replace; boundary=frame' } });
  };
  w.eval(bundle.outputFiles[0].text);
  await until(() => requests.length >= 2);
  assert(requests[0].signal.aborted, 'StrictMode disposes first effect');
  requests.at(-1).emit(); await until(() => w.document.querySelector('img'));
  const firstUrl = w.document.querySelector('img').src;
  w.__render('/second'); await until(() => requests.at(-1).url === '/second');
  assert(requests.at(-2).signal.aborted, 'source change aborts old request');
  assert(!w.document.querySelector('img'), 'old source frame disappears before new stream decodes');
  assert(revoked.includes(firstUrl));
  requests.at(-1).emit(); await until(() => w.document.querySelector('img'));
  assert(w.__ready >= 2);
  const activeRequest = requests.at(-1); const timeout = [...watchdogs.values()].at(-1); timeout(); await tick();
  assert(activeRequest.signal.aborted); assert.equal(w.__failed, 1); assert(!w.document.querySelector('img'), 'idle timeout clears stale frame');
  w.__render('/third'); await until(() => requests.at(-1).url === '/third'); requests.at(-1).emit(); await until(() => w.document.querySelector('img'));
  w.__unmount(); await tick(); assert(requests.at(-1).signal.aborted);
  assert.equal(watchdogs.size, 0); assert.deepEqual([...revoked].sort(), [...created].sort(), 'all owned URLs released once');
  dom.window.close(); console.log('PASS: StrictMode, source changes, watchdog, stale frames, abort and Blob cleanup');
})().catch(error => { console.error(error); process.exit(1); });
