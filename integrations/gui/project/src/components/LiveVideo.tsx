import { Capacitor } from '@capacitor/core';
import { useEffect, useState } from 'react';
import { readMjpegStream } from '@/services/mjpeg';

export function LiveVideo({ src, onError, onReady }: { src: string; onError: () => void; onReady: () => void }) {
  const native = Capacitor.isNativePlatform();
  const [frame, setFrame] = useState<{ source: string; url: string } | null>(null);
  useEffect(() => {
    if (!native) return;
    const controller = new AbortController();
    let active = true, failed = false;
    let displayed = '', pending = '';
    let decoder: HTMLImageElement | null = null;
    let timer: ReturnType<typeof setTimeout>;
    function clearImages() {
      if (decoder) { decoder.onload = null; decoder.onerror = null; decoder.src = ''; decoder = null; }
      if (pending) URL.revokeObjectURL(pending);
      if (displayed) URL.revokeObjectURL(displayed);
      pending = displayed = '';
    }
    function fail() {
      if (!active || failed) return;
      failed = true; clearTimeout(timer); controller.abort(); clearImages(); setFrame(null); onError();
    }
    function watchdog() { clearTimeout(timer); timer = setTimeout(fail, 10000); }
    setFrame(null); watchdog();
    void readMjpegStream(src, controller.signal, bytes => {
      if (!active || failed || pending) return;
      const url = URL.createObjectURL(new Blob([bytes.slice().buffer], { type: 'image/jpeg' }));
      pending = url; decoder = new Image();
      decoder.onload = () => {
        if (!active || failed) return;
        const previous = displayed; displayed = url; pending = ''; decoder = null;
        setFrame({ source: src, url }); if (previous) URL.revokeObjectURL(previous);
        watchdog(); onReady();
      };
      decoder.onerror = fail;
      decoder.src = url;
    }).catch(() => { if (!controller.signal.aborted) fail(); });
    return () => { active = false; clearTimeout(timer); controller.abort(); clearImages(); };
  }, [native, src, onError, onReady]);
  if (!native) return <img src={src} onError={onError} onLoad={onReady} alt="共享摄像头实时画面" />;
  return frame?.source === src
    ? <img src={frame.url} onError={onError} alt="共享摄像头实时画面" />
    : <div className="preview-placeholder" role="status">正在连接实时画面…</div>;
}
