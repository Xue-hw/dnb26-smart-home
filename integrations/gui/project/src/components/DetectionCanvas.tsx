import { useEffect, useRef, useState } from 'react';
import type { Detection } from '@/types/contracts';
import { loadMediaImage } from '@/services/mediaImage';
import { faceStyle, objectStyle, type FaceAnnotation } from '@/services/recognitionStyles';

const noFaces: FaceAnnotation[] = [];

export function DetectionCanvas({ imageUrl, detections, faces = noFaces }: { imageUrl: string; detections: Detection[]; faces?: FaceAnnotation[] }) {
  const [failed, setFailed] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    setFailed(false);
    const canvas = canvasRef.current;
    canvas?.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
    const controller = new AbortController();
    let release: (() => void) | undefined;
    void loadMediaImage(imageUrl, controller.signal).then(resource => {
      if (controller.signal.aborted) { resource.release(); return; }
      release = resource.release;
      const image = resource.image;
      const canvas = canvasRef.current;
      const context = canvas?.getContext('2d');
      if (!canvas || !context) return;
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0);
      const lineWidth = Math.max(2, Math.round(Math.min(canvas.width, canvas.height) * 0.005));
      const fontSize = Math.max(14, Math.round(Math.min(canvas.width, canvas.height) * 0.032));
      const annotations = [
        ...detections.map(detection => ({ bbox: detection.bbox, style: objectStyle(detection),
          text: `${objectStyle(detection).label} · ${detection.label_zh} ${(detection.confidence * 100).toFixed(0)}%` })),
        ...faces.map(face => ({ bbox: face.bbox, style: faceStyle(face, 'upload'), text: faceStyle(face, 'upload').label })),
      ];
      annotations.forEach(annotation => {
        const [x1, y1, x2, y2] = annotation.bbox;
        const color = annotation.style.color;
        context.strokeStyle = color;
        context.lineWidth = lineWidth;
        context.strokeRect(x1, y1, x2 - x1, y2 - y1);
        const label = annotation.text;
        context.font = `600 ${fontSize}px "Microsoft YaHei", sans-serif`;
        const padding = Math.min(8, canvas.width / 8);
        const maxTextWidth = Math.max(1, canvas.width - padding * 2);
        const lines: string[] = [];
        let line = '';
        for (const character of label) {
          if (line && context.measureText(line + character).width > maxTextWidth) { lines.push(line); line = ''; }
          line += character;
        }
        if (line) lines.push(line);
        const labelWidth = Math.min(canvas.width, Math.max(...lines.map(text => context.measureText(text).width), 0) + padding * 2);
        const lineHeight = fontSize + 6;
        const labelHeight = lines.length * lineHeight + 6;
        const labelX = Math.max(0, Math.min(x1, canvas.width - labelWidth));
        const labelY = Math.max(0, Math.min(y1 - labelHeight, canvas.height - labelHeight));
        context.fillStyle = color;
        context.fillRect(labelX, labelY, labelWidth, labelHeight);
        context.fillStyle = annotation.style.textColor;
        context.textBaseline = 'middle';
        lines.forEach((text, index) => context.fillText(text, labelX + padding, labelY + 3 + (index + .5) * lineHeight, maxTextWidth));
      });
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { controller.abort(); release?.(); };
  }, [imageUrl, detections, faces]);

  return <>{failed && <p role="alert">图片读取失败，请重新获取照片或选择其他图片。</p>}<canvas style={{ display: failed ? 'none' : 'block' }} ref={canvasRef} aria-label="识别结果图，框旁文字标明模型来源或人脸状态" /></>;
}
