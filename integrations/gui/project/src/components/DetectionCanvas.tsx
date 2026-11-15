import { useEffect, useRef, useState } from 'react';
import type { Detection } from '@/types/contracts';

export function DetectionCanvas({ imageUrl, detections }: { imageUrl: string; detections: Detection[] }) {
  const [failed, setFailed] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    setFailed(false);
    const canvas = canvasRef.current;
    canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
    const image = new Image();
    image.onerror = () => setFailed(true);
    image.onload = () => {
      const canvas = canvasRef.current;
      const context = canvas?.getContext('2d');
      if (!canvas || !context) return;
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0);
      const colors = ['#35d0a0', '#20aee5', '#f0b657'];
      const lineWidth = Math.max(2, Math.round(Math.min(canvas.width, canvas.height) * 0.005));
      const fontSize = Math.max(14, Math.round(Math.min(canvas.width, canvas.height) * 0.032));
      detections.forEach((detection, index) => {
        const [x1, y1, x2, y2] = detection.bbox;
        const color = colors[index % colors.length];
        context.strokeStyle = color;
        context.lineWidth = lineWidth;
        context.strokeRect(x1, y1, x2 - x1, y2 - y1);
        const label = `${detection.label_zh} ${(detection.confidence * 100).toFixed(0)}%`;
        context.font = `600 ${fontSize}px "Microsoft YaHei", sans-serif`;
        const textWidth = context.measureText(label).width;
        const labelHeight = fontSize + 12;
        const labelY = Math.max(0, y1 - labelHeight);
        context.fillStyle = color;
        context.fillRect(x1, labelY, textWidth + 16, labelHeight);
        context.fillStyle = '#07111f';
        context.textBaseline = 'middle';
        context.fillText(label, x1 + 8, labelY + labelHeight / 2);
      });
    };
    image.src = imageUrl;
    return () => { image.onload = null; image.onerror = null; };
  }, [imageUrl, detections]);

  return <>{failed && <p role="alert">图片读取失败，请重新获取照片或选择其他图片。</p>}<canvas style={{ display: failed ? 'none' : 'block' }} ref={canvasRef} aria-label="物体识别结果图" /></>;
}
