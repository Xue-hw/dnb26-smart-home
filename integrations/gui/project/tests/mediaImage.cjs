const { build } = require('esbuild');
const { JSDOM } = require('jsdom');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
(async () => {
  const bundle = await build({ stdin: { contents: `import {createRoot} from 'react-dom/client';
    import {DetectionCanvas} from './src/components/DetectionCanvas';
    const root=createRoot(document.getElementById('root'));
    window.__unmount=()=>root.unmount();
    root.render(<DetectionCanvas imageUrl="http://10.84.15.226:18080/uploads/captures/test.jpg" detections={[]} />);`, resolveDir: root, loader: 'tsx' },
    bundle: true, write: false, format: 'iife', tsconfig: path.join(root, 'tsconfig.json'),
    plugins: [{ name: 'native', setup(b) {
      b.onResolve({ filter: /^@capacitor\/core$/ }, () => ({ path: 'native', namespace: 'fixture' }));
      b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const Capacitor={isNativePlatform:()=>true};' }));
    } }],
  });
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://localhost', runScripts: 'outside-only' });
  const w = dom.window, revoked = []; let drawn = 0, fetched = 0;
  w.HTMLCanvasElement.prototype.getContext = () => ({ clearRect() {}, drawImage() { drawn++; } });
  w.Image = class {
    naturalWidth = 640; naturalHeight = 480;
    set src(value) { if (value) queueMicrotask(() => value.startsWith('http:') ? this.onerror?.() : this.onload?.()); }
  };
  w.URL.createObjectURL = () => 'blob:https://localhost/test';
  w.URL.revokeObjectURL = url => revoked.push(url);
  w.fetch = async () => { fetched++; return new Response(new Uint8Array([255, 216, 255, 217]), { headers: { 'Content-Type': 'image/jpeg' } }); };
  w.TextEncoder = TextEncoder; w.TextDecoder = TextDecoder;
  w.eval(bundle.outputFiles[0].text);
  for (let i = 0; i < 50 && !drawn && !w.document.querySelector('[role=alert]'); i++) await tick();
  assert.equal(drawn, 1, 'native captured image must draw through a Blob rather than fail as an HTTP image');
  assert.equal(fetched, 1);
  assert.equal(w.document.querySelector('[role=alert]'), null);
  w.__unmount(); await tick();
  assert.deepEqual(revoked, ['blob:https://localhost/test'], 'owned image URL must be released on unmount');
  dom.window.close();
  console.log('PASS: native capture preview draws fetched image and releases Blob URL');
})().catch(error => { console.error(error); process.exit(1); });
