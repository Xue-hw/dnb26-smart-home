const { build } = require('esbuild');
const { JSDOM } = require('jsdom');
const assert = require('node:assert/strict');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const tick = () => new Promise(resolve => setTimeout(resolve, 20));
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const stamp = '2026-11-16T14:00:00Z';
const status = { backend: 'online', server_time: stamp };
const snapshot = temperature => ({ freshness: 'live', server_time: stamp, sensors: [{ metric: 'temperature', value: temperature }] });

(async () => {
  const bundle = await build({
    stdin: {
      contents: `import { StrictMode, useLayoutEffect } from 'react';
        import { createRoot } from 'react-dom/client';
        import { AppDataProvider, useAppData } from './src/context/AppDataContext';
        import { createRefreshQueue } from './src/services/refreshQueue';
        window.__createRefreshQueue = createRefreshQueue;
        function Probe() {
          const value = useAppData();
          useLayoutEffect(() => { window.__app = value; });
          return <output>{value.snapshot?.sensors[0]?.value ?? '待接入'}</output>;
        }
        const root = createRoot(document.getElementById('root'));
        window.__unmount = () => root.unmount();
        const app = <AppDataProvider><Probe /></AppDataProvider>;
        root.render(window.__strict ? <StrictMode>{app}</StrictMode> : app);`,
      resolveDir: root, loader: 'tsx', sourcefile: 'refresh-test.tsx',
    },
    bundle: true, write: false, format: 'iife', tsconfig: path.join(root, 'tsconfig.json'),
    plugins: [{
      name: 'controlled-data-source',
      setup(builder) {
        builder.onResolve({ filter: /^@\/services$/ }, () => ({ path: 'source', namespace: 'controlled' }));
        builder.onLoad({ filter: /.*/, namespace: 'controlled' }, () => ({
          contents: "export const dataMode = 'http'; export const dataSource = window.__source;",
        }));
      },
    }],
  });

  async function start(strict = false) {
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost', runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window, statuses = [], snapshots = [], intervals = new Set();
    w.__strict = strict;
    let onEvent, unsubscribed = false;
    w.setInterval = callback => { intervals.add(callback); return callback; };
    w.clearInterval = callback => intervals.delete(callback);
    w.__source = {
      getSystemStatus() { const gate = deferred(); statuses.push(gate); return gate.promise; },
      getDashboardSnapshot() { const gate = deferred(); snapshots.push(gate); return gate.promise; },
      subscribeEvents(callback) { onEvent = callback; return () => { unsubscribed = true; onEvent = undefined; }; },
      sendDeviceCommand: async () => ({ command_id: 'test-command', status: 'acked', source: 'gateway' }),
    };
    w.eval(bundle.outputFiles[0].text);
    for (let i = 0; i < 50 && (!onEvent || !w.__app); i++) await tick();
    assert(onEvent, 'provider subscribes to events');
    return {
      w, statuses, snapshots, intervals,
      emit(type = 'device.state.changed') { onEvent?.({ type }); },
      async finish(index, temperature = 26.6) { statuses[index].resolve(status); snapshots[index].resolve(snapshot(temperature)); await tick(); },
      reading() { return w.document.querySelector('output')?.textContent; },
      async close() { w.__unmount(); await tick(); dom.window.close(); },
      isUnsubscribed: () => unsubscribed,
    };
  }

  const tests = [
    ['event bursts do not create overlapping status/snapshot request pairs', async h => {
      for (let i = 0; i < 100; i++) h.emit();
      assert.equal(h.statuses.length, 1);
      assert.equal(h.snapshots.length, 1);
      await h.finish(0);
      assert.equal(h.statuses.length, 2, 'burst becomes one trailing refresh');
    }],
    ['a completed snapshot reaches the screen despite newer events', async h => {
      for (let i = 0; i < 25; i++) h.emit();
      await h.finish(0, 27.1);
      assert.equal(h.reading(), '27.1');
      assert(h.w.__app.lastSuccess > 0);
    }],
    ['sustained events update readings on each completed batch', async h => {
      for (let batch = 0; batch < 4; batch++) {
        for (let i = 0; i < 25; i++) h.emit(i % 2 ? 'sensor.updated' : 'device.state.changed');
        assert.equal(h.statuses.length, batch + 1);
        await h.finish(batch, 25 + batch);
        assert.equal(h.reading(), String(25 + batch));
      }
      await h.finish(4, 29);
      assert.equal(h.reading(), '29');
      assert.equal(h.statuses.length, 5);
    }],
    ['explicit refresh waits for a batch requested after the call without waiting forever', async h => {
      let done = false;
      const request = h.w.__app.refresh().then(() => { done = true; });
      await h.finish(0, 20);
      assert.equal(done, false);
      h.emit();
      await h.finish(1, 21);
      await request;
      assert.equal(done, true);
      assert.equal(h.reading(), '21');
      assert.equal(h.statuses.length, 3, 'later events remain in their own batch');
    }],
    ['failed requests remain visible, retain data and recover on the next complete batch', async h => {
      await h.finish(0, 26);
      const failed = h.w.__app.refresh();
      h.statuses[1].reject(new h.w.Error('diagnostic connection failure'));
      await tick();
      h.emit();
      assert.equal(h.statuses.length, 2, 'the other half of the failed pair is still pending');
      h.snapshots[1].resolve(snapshot(99));
      await failed; await tick();
      assert.match(h.w.__app.connectionError, /diagnostic connection failure/);
      assert.equal(h.reading(), '26', 'never partially apply a failed pair');
      await h.finish(2, 28);
      assert.equal(h.reading(), '28');
      assert.equal(h.w.__app.connectionError, '');
    }],
    ['unmount cancels queued refreshes and releases event and polling subscriptions', async h => {
      h.emit();
      const waiting = h.w.__app.refresh();
      h.w.__unmount();
      await waiting;
      h.statuses[0].resolve(status); h.snapshots[0].resolve(snapshot(26));
      await tick();
      assert.equal(h.statuses.length, 1);
      assert.equal(h.intervals.size, 0);
      assert(h.isUnsubscribed());
    }],
    ['polling and manual refresh recover without event-stream availability', async h => {
      await h.finish(0, 23);
      for (const poll of h.intervals) poll();
      await h.finish(1, 24);
      assert.equal(h.reading(), '24');
      const manual = h.w.__app.refresh();
      await h.finish(2, 25); await manual;
      assert.equal(h.reading(), '25');
    }],
    ['a control receipt completes after fresh data even during continuing events', async h => {
      const command = h.w.__app.sendCommand({ device_id: 'main_light', action: 'set', params: { power: false } });
      await tick();
      h.emit();
      await h.finish(0, 23);
      h.emit();
      await h.finish(1, 24);
      const receipt = await command;
      await tick();
      assert.equal(receipt.status, 'acked');
      assert.equal(h.w.__app.pendingCommands.main_light, false);
      assert.equal(h.reading(), '24');
    }],
    ['queue failures reject the correct caller while a queued retry can recover', async h => {
      const reads = [];
      const queue = h.w.__createRefreshQueue(() => { const gate = deferred(); reads.push(gate); return gate.promise; });
      const first = queue.request();
      const failure = assert.rejects(first, /temporary failure/);
      const next = queue.request();
      reads[0].reject(new Error('temporary failure'));
      await failure;
      assert.equal(reads.length, 2);
      reads[1].resolve(); await next;
      queue.dispose(); await queue.request(); queue.dispose();
      assert.equal(reads.length, 2, 'a disposed queue never starts another read');
    }],
    ['effect replay cannot apply a disposed provider generation or cancel the new one', async h => {
      assert.equal(h.statuses.length, 2);
      await h.finish(0, 90);
      assert.equal(h.reading(), '待接入');
      await h.finish(1, 26);
      assert.equal(h.reading(), '26');
      assert.equal(h.intervals.size, 1);
    }, true],
  ];
  let failed = 0;
  for (const [name, test, strict] of tests) {
    const h = await start(strict);
    let timeout;
    try {
      await Promise.race([test(h), new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('refresh did not settle')), 2000); })]);
      console.log('PASS:', name);
    }
    catch (error) { failed++; console.error('FAIL:', name, error.message); }
    finally { clearTimeout(timeout); await h.close(); }
  }
  console.log(`Refresh regression: ${tests.length - failed}/${tests.length} passed`);
  process.exitCode = failed ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 1; });
