interface RefreshBatch {
  promise: Promise<void>;
  resolve: () => void;
  reject: (reason: unknown) => void;
}

// A caller arriving during a read waits for the next batch, not an older snapshot
// or an endless stream of future events. Each batch has its own completion promise.
export function createRefreshQueue(read: () => Promise<void>) {
  let running = false;
  let disposed = false;
  let pending: RefreshBatch | undefined;

  async function run(batch: RefreshBatch) {
    running = true;
    try {
      await read();
      batch.resolve();
    } catch (reason) {
      batch.reject(reason);
    } finally {
      running = false;
      const next = pending;
      pending = undefined;
      if (next) {
        if (disposed) next.resolve();
        else void run(next);
      }
    }
  }

  return {
    request(): Promise<void> {
      if (disposed) return Promise.resolve();
      if (pending) return pending.promise;
      let resolve!: () => void;
      let reject!: (reason: unknown) => void;
      const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
      const batch = { promise, resolve, reject };
      if (running) pending = batch;
      else void run(batch);
      return promise;
    },
    dispose() {
      disposed = true;
      pending?.resolve();
      pending = undefined;
    },
  };
}
