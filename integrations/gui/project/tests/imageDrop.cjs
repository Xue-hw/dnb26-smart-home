const { build } = require('esbuild');
const { JSDOM } = require('jsdom');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
(async () => {
  const bundle = await build({ stdin: { contents: `import {createRoot} from 'react-dom/client';import MonitorPage from './src/pages/MonitorPage';
    const root=createRoot(document.getElementById('root'));window.__unmount=()=>root.unmount();root.render(<MonitorPage/>);`, resolveDir: root, loader: 'tsx' },
    bundle: true, write: false, format: 'iife', tsconfig: path.join(root, 'tsconfig.json'), plugins: [{ name: 'fixtures', setup(b) {
      for (const [pattern, name] of [[/^@\/context\/AppDataContext$/, 'context'], [/^@\/components\/LiveMonitor$/, 'live'], [/^@\/components\/DetectionCanvas$/, 'canvas'], [/^@\/services\/mediaImage$/, 'image']]) {
        b.onResolve({ filter: pattern }, () => ({ path: name, namespace: 'fixture' }));
      }
      b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ contents: {
        context: "export const useAppData=()=>({source:window.__source,mode:'http'});",
        live: 'export const LiveMonitor=()=>null;',
        canvas: 'export const DetectionCanvas=()=>null;',
        image: 'export const loadMediaImage=(url,signal)=>window.__loadMediaImage(url,signal);',
      }[args.path] }));
    } }] });
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://localhost', runScripts: 'outside-only' });
  const w = dom.window, created = [], revoked = [], requests = [];
  let finish;
  w.__loadMediaImage = async () => ({ image: { naturalWidth: 640, naturalHeight: 480 }, release() {} });
  w.URL.createObjectURL = file => { created.push(file.name); return 'blob:https://localhost/'+created.length; };
  w.URL.revokeObjectURL = url => revoked.push(url);
  w.__source = { getRecognitionEvents: async () => ({ items: [] }), detectObjects: input => { requests.push(input); return new Promise(resolve => { finish = resolve; }); } };
  w.eval(bundle.outputFiles[0].text); await tick(); await tick();
  const zone = w.document.querySelector('[aria-label="上传识别图片"]');
  assert(zone, 'recognition preview must be a file drop area as well as supporting its picker');
  for (const relatedTarget of [null, zone.firstElementChild, w]) {
    const leave = new w.Event('dragleave', { bubbles: true }); Object.defineProperty(leave, 'relatedTarget', { value: relatedTarget });
    assert.doesNotThrow(() => zone.dispatchEvent(leave));
  }
  const drop = files => { const event = new w.Event('drop', { bubbles: true, cancelable: true }); Object.defineProperty(event, 'dataTransfer', { value: { files } }); zone.dispatchEvent(event); return event; };
  const file = new w.File(['jpeg'], 'car.jpg', { type: 'image/jpeg' });
  assert(drop([file]).defaultPrevented, 'drop cannot navigate away from application'); await tick();
  assert(w.document.body.textContent.includes('car.jpg')); assert.deepEqual(created, ['car.jpg']);
  const click = label => Array.from(w.document.querySelectorAll('button')).find(button => button.textContent === label).click();
  click('开始识别'); await tick(); assert.equal(requests[0].image.name, 'car.jpg');
  drop([new w.File(['x'], 'busy.jpg', { type: 'image/jpeg' })]); await tick(); assert.deepEqual(created, ['car.jpg'], 'busy detection must retain its input');
  finish({ detections: [], count: 0, message: 'ok', inference_ms: 1 }); await tick(); await tick();
  drop([file, file]); await tick(); assert(w.document.body.textContent.includes('一次只选择一张图片'));
  drop([new w.File(['bad'], 'bad.txt', { type: 'text/plain' })]); await tick(); assert(w.document.body.textContent.includes('请选择图片文件'));
  const oversized = new w.File(['x'], 'huge.jpg', { type: 'image/jpeg' }); Object.defineProperty(oversized, 'size', { value: 8*1024*1024+1 });
  drop([oversized]); await tick(); assert(w.document.body.textContent.includes('8 MB'));
  assert.deepEqual(created, ['car.jpg'], 'invalid files must not replace the valid preview');
  const picker = w.document.querySelector('input[type=file]');
  Object.defineProperty(picker, 'files', { configurable: true, value: [new w.File(['png'], 'chosen.png', { type: 'image/png' })] });
  picker.dispatchEvent(new w.Event('change', { bubbles: true })); await tick();
  assert(w.document.body.textContent.includes('chosen.png')); assert.deepEqual(created, ['car.jpg', 'chosen.png']);
  let resolveImage, imageSignal, released = 0;
  w.__loadMediaImage = (_, signal) => { imageSignal = signal; return new Promise(resolve => { resolveImage = resolve; }); };
  click('开始识别'); await tick(); w.__unmount(); await tick(); assert(imageSignal.aborted, 'page unmount cancels pending image read');
  resolveImage({ image: { naturalWidth: 640, naturalHeight: 480 }, release() { released++; } }); await tick();
  assert.equal(requests.length, 1, 'late image load after unmount must not submit a new recognition');
  assert.equal(released, 1); assert.equal(revoked.length, 2); dom.window.close();
  console.log('PASS: drag/drop and picker, validation, busy guard and URL cleanup');
})().catch(error => { console.error(error); process.exit(1); });
