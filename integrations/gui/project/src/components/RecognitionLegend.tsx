import { recognitionPalette } from '@/services/recognitionStyles';

export function RecognitionLegend() {
  return <div role="note" aria-label="识别框颜色说明" className="form-help" style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 16px', margin: '12px 0' }}>
    {Object.entries(recognitionPalette).map(([key, style]) => <span key={key} style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
      <span aria-hidden="true" style={{ width: 12, height: 12, border: `2px solid ${style.color}`, flexShrink: 0 }} />{style.label}
    </span>)}
    <span>状态文字显示身份、活体核验及通行资格；开门执行结果请查看设备回执和现场门状态。</span>
  </div>;
}
