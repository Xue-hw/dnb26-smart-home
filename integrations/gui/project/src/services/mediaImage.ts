import { Capacitor } from '@capacitor/core';

const MAX_IMAGE_BYTES = 8 * 1024 * 1024;

async function fetchImage(url: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(url, { signal, cache: 'no-store', credentials: 'omit' });
  const reader = response.body?.getReader();
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  let type = '';
  try {
    if (!response.ok) throw new Error(`图片读取失败（HTTP ${response.status}）。`);
    type = response.headers.get('content-type')?.split(';')[0] || '';
    if (!type.startsWith('image/')) throw new Error('后端未返回有效图片。');
    if (Number(response.headers.get('content-length')) > MAX_IMAGE_BYTES) throw new Error('图片超过 8 MB。');
    if (!reader) throw new Error('图片没有可读取的数据。');
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MAX_IMAGE_BYTES) throw new Error('图片超过 8 MB。');
      chunks.push(value.slice());
    }
  } finally {
    // Preserve the original read/size error when cancellation also fails.
    if (reader) { await reader.cancel().catch(() => undefined); reader.releaseLock(); }
  }
  return new Blob(chunks, { type });
}

/** Caller owns release(); only URLs created here are revoked here. */
export async function loadMediaImage(url: string, signal?: AbortSignal): Promise<{ image: HTMLImageElement; release: () => void }> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  if (signal?.aborted) controller.abort();
  else signal?.addEventListener('abort', abortFromCaller, { once: true });
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
  const loadingSignal = controller.signal;
  try {
    const blob = Capacitor.isNativePlatform() && /^http:\/\//i.test(url) ? await fetchImage(url, loadingSignal) : null;
    if (loadingSignal.aborted) throw new DOMException('已取消图片加载。', 'AbortError');
    const ownedUrl = blob ? URL.createObjectURL(blob) : '';
    const image = new Image();
    return await new Promise<{ image: HTMLImageElement; release: () => void }>((resolve, reject) => {
      let released = false;
      const release = () => {
        if (released) return;
        released = true;
        image.onload = null; image.onerror = null; image.src = '';
        if (ownedUrl) URL.revokeObjectURL(ownedUrl);
        loadingSignal.removeEventListener('abort', abort);
      };
      const abort = () => { release(); reject(new DOMException('已取消图片加载。', 'AbortError')); };
      image.onload = () => {
        loadingSignal.removeEventListener('abort', abort);
        image.onload = null; image.onerror = null;
        resolve({ image, release });
      };
      image.onerror = () => { release(); reject(new Error('图片读取失败，请重新获取照片或选择其他图片。')); };
      loadingSignal.addEventListener('abort', abort, { once: true });
      image.src = ownedUrl || url;
    });
  } catch (error) {
    if (timedOut) throw new Error('图片读取超时，请重试。');
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
