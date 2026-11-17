const MAX_HEADER_BYTES = 8192;
const MAX_FRAME_BYTES = 2 * 1024 * 1024;
const encoder = new TextEncoder();

function indexOfBytes(bytes: Uint8Array, pattern: Uint8Array): number {
  outer: for (let i = 0; i <= bytes.length - pattern.length; i++) {
    for (let j = 0; j < pattern.length; j++) if (bytes[i + j] !== pattern[j]) continue outer;
    return i;
  }
  return -1;
}

export function mjpegBoundary(contentType: string): string {
  const match = /^multipart\/x-mixed-replace\s*;\s*boundary=(?:"([^"\r\n]+)"|([^;\s]+))/i.exec(contentType);
  const boundary = match?.[1] || match?.[2] || '';
  if (!/^[\w'()+,./:=?-]{1,70}$/.test(boundary)) throw new Error('实时视频格式无效。');
  return boundary;
}

/** Bounded multipart parser. Each push returns only its newest complete JPEG. */
export class MjpegParser {
  private buffer: Uint8Array = new Uint8Array();
  private stage: 'boundary' | 'headers' | 'image' = 'boundary';
  private readonly boundary: Uint8Array;
  private readonly separator: Uint8Array;
  private ended = false;
  constructor(boundary: string, private readonly maxFrameBytes = MAX_FRAME_BYTES) {
    mjpegBoundary(`multipart/x-mixed-replace; boundary="${boundary}"`);
    this.boundary = encoder.encode(`--${boundary}`);
    this.separator = encoder.encode(`\r\n--${boundary}`);
  }

  push(chunk: Uint8Array): Uint8Array | undefined {
    let latest: Uint8Array | undefined;
    // Limit temporary allocations even if a transport delivers many frames at once.
    for (let offset = 0; offset < chunk.length; offset += 16384) {
      if (this.ended) break;
      const part = chunk.subarray(offset, offset + 16384);
      const joined = new Uint8Array(this.buffer.length + part.length);
      joined.set(this.buffer); joined.set(part, this.buffer.length); this.buffer = joined;
      for (;;) {
        if (this.stage === 'boundary') {
          const start = indexOfBytes(this.buffer, this.boundary);
          if (start > MAX_HEADER_BYTES) throw new Error('实时视频头部过长。');
          if (start < 0) {
            if (this.buffer.length > MAX_HEADER_BYTES) throw new Error('实时视频边界无效。');
            break;
          }
          if (this.buffer.length < start + this.boundary.length + 2) break;
          const suffix = this.buffer.subarray(start + this.boundary.length, start + this.boundary.length + 2);
          if (suffix[0] === 45 && suffix[1] === 45) { this.ended = true; this.buffer = new Uint8Array(); break; }
          if (suffix[0] !== 13 || suffix[1] !== 10) throw new Error('实时视频边界无效。');
          this.buffer = this.buffer.slice(start + this.boundary.length + 2); this.stage = 'headers';
        }
        if (this.stage === 'headers') {
          const end = indexOfBytes(this.buffer, encoder.encode('\r\n\r\n'));
          if (end < 0) {
            if (this.buffer.length > MAX_HEADER_BYTES) throw new Error('实时视频头部过长。');
            break;
          }
          if (end > MAX_HEADER_BYTES || !/^content-type:\s*image\/jpeg\s*$/im.test(new TextDecoder().decode(this.buffer.subarray(0, end)))) {
            throw new Error('实时视频帧格式无效。');
          }
          this.buffer = this.buffer.slice(end + 4); this.stage = 'image';
        }
        if (this.stage === 'image') {
          const end = indexOfBytes(this.buffer, this.separator);
          if (end < 0) {
            if (this.buffer.length > this.maxFrameBytes + this.separator.length) throw new Error('实时视频帧过大。');
            break;
          }
          if (end > this.maxFrameBytes || end < 4 || this.buffer[0] !== 255 || this.buffer[1] !== 216 || this.buffer[end - 2] !== 255 || this.buffer[end - 1] !== 217) {
            throw new Error('实时视频 JPEG 帧无效。');
          }
          latest = this.buffer.slice(0, end);
          this.buffer = this.buffer.slice(end + 2); this.stage = 'boundary';
        }
      }
    }
    return latest;
  }
}

export async function readMjpegStream(url: string, signal: AbortSignal, onFrame: (frame: Uint8Array) => void): Promise<void> {
  const response = await fetch(url, { signal, cache: 'no-store', credentials: 'omit' });
  const reader = response.body?.getReader();
  try {
    if (!response.ok) throw new Error(`实时视频请求失败（HTTP ${response.status}）。`);
    const parser = new MjpegParser(mjpegBoundary(response.headers.get('content-type') || ''));
    if (!reader) throw new Error('实时视频没有可读取的数据。');
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (signal.aborted) return;
      if (done) throw new Error('实时视频已断开，请重新连接画面。');
      const frame = parser.push(value);
      if (frame) onFrame(frame);
    }
  } finally {
    // Cleanup failure must not replace the original network/parser error.
    if (reader) { await reader.cancel().catch(() => undefined); reader.releaseLock(); }
  }
}
