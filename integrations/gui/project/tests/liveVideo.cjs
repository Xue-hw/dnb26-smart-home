const { build } = require('esbuild');
const { JSDOM } = require('jsdom');
const assert = require('node:assert/strict');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
async function until(check) {
  for (let i = 0; i < 80; i++) { if (check()) return; await tick(); }
  assert(check(), 'expected asynchronous video state');
}

(async () => {
  const bundle = await build({
    stdin: { contents: `import { createRoot } from 'react-dom/client';
      import { LiveMonitor } from './src/components/LiveMonitor';
      const root = createRoot(document.getElementById('root'));
      window.__unmount = () => root.unmount();
      root.render(<LiveMonitor />);`, resolveDir: root, loader: 'tsx' },
    bundle: true, write: false, format: 'iife', tsconfig: path.join(root, 'tsconfig.json'),
    plugins: [{ name: 'video-fixtures', setup(builder) {
      builder.onResolve({ filter: /^@\/context\/AppDataContext$/ }, () => ({ path: 'context', namespace: 'fixtures' }));
      builder.onResolve({ filter: /^@\/services\/connection$/ }, () => ({ path: 'connection', namespace: 'fixtures' }));
      builder.onResolve({ filter: /^@capacitor\/core$/ }, () => ({ path: 'capacitor', namespace: 'fixtures' }));
      builder.onLoad({ filter: /.*/, namespace: 'fixtures' }, args => ({ contents: args.path === 'context'
        ? "export function useAppData(){return {source:window.__source,mode:'http'};}"
        : args.path === 'connection' ? "export const backendUrl = path => 'http://10.84.15.226:18080'+path;"
        : 'export const Capacitor = {isNativePlatform:()=>window.__native};' }));
    } }],
  });
  for (const native of [true, false]) {
    const dom = new JSDOM('<div id="root"></div>', { url: 'https://localhost', runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window; w.__native = native;
    const stamp = new Date().toISOString();
    w.__source = { getLiveVision: async () => ({ camera_status: 'online', frame_id: 1, captured_at: stamp, server_time: stamp, faces: [], objects: [] }) };
    w.fetch = () => new Promise(() => {});
    w.eval(bundle.outputFiles[0].text);
    await until(() => w.document.body.textContent.includes('实时输入'));
    await tick();
    const direct = Array.from(w.document.images).some(img => img.src.startsWith('http:'));
    assert.equal(direct, !native, 'native must fetch video instead of using a mixed-content HTTP image; browser keeps MJPEG image');
    w.__unmount(); dom.window.close();
  }
  console.log('PASS: physical-APK transport selection regression (jsdom is engineering evidence only)');
})().catch(error => { console.error(error); process.exit(1); });
