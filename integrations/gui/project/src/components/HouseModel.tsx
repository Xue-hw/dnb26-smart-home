import { useEffect, useRef, useState } from 'react';
import { Box, RotateCcw, ScanLine } from 'lucide-react';
import type { HouseView, SceneState } from './houseScene';

interface HouseModelProps extends SceneState {
  windowOpen?: boolean; windowAvailable?: boolean; doorActuatorOnly?: boolean;
  temperature?: number; humidity?: number;
}
type SceneController = Awaited<ReturnType<typeof import('./houseScene')['createHouseScene']>>;

export function HouseModel(props: HouseModelProps) {
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<SceneController | null>(null);
  const current = useRef(props);
  const [view, setView] = useState<HouseView>('perspective');
  const [fallback, setFallback] = useState(false);
  const chosenView = useRef<HouseView>('perspective');
  useEffect(() => { current.current = props; controller.current?.update(props); }, [props]);
  useEffect(() => {
    let cancelled = false;
    if (!window.WebGLRenderingContext || !host.current) return;
    void import('./houseScene').then(module => {
      if (cancelled || !host.current) return;
      controller.current = module.createHouseScene(host.current, current.current, () => { if (!cancelled) setFallback(true); });
      controller.current.view(chosenView.current);
    }).catch(() => { if (!cancelled) setFallback(true); });
    return () => { cancelled = true; controller.current?.dispose(); controller.current = null; };
  }, []);
  function choose(next: HouseView) { chosenView.current = next; setView(next); controller.current?.view(next); }
  const hasWebGL = typeof window.WebGLRenderingContext !== 'undefined';
  const powerText = (value?: boolean) => value === undefined ? '未知' : value ? '开启' : '关闭';
  return <div className="house-model" aria-label="家居三维模拟视图">
    <div className="scene-toolbar"><span><Box size={15} />空间模型 <small>01 / HOME</small></span><div role="group" aria-label="模型视角">{([['perspective', '立体'], ['plan', '俯视'], ['entrance', '正面']] as const).map(([key, label]) => <button key={key} aria-pressed={view === key} onClick={() => choose(key)}>{label}</button>)}<button onClick={() => choose('perspective')} aria-label="复位模型视角"><RotateCcw size={14} /></button></div></div>
    <div className="model-canvas" ref={host} aria-hidden="true" />
    {(!hasWebGL || fallback) && <div className="model-fallback"><Box size={34} /><strong>空间模型暂不可用</strong><p>当前浏览器未提供 3D 渲染，设备状态仍可在下方查看。</p></div>}
    <div className="model-room-labels" aria-hidden="true"><span>起居室</span><span>车库</span></div>
    <div className="scene-status" aria-label="模型设备反馈"><span data-active={props.doorOpen}>入户门 · {props.doorOpen === undefined ? '未知' : props.doorOpen ? '开启' : '关闭'}</span><span>车库门 · {({ open: '开启', closed: '关闭', moving: '移动中' } as Record<string, string>)[props.garagePosition || ''] || '未知'}</span><span data-active={props.lightOn}>灯{powerText(props.lightOn)}{typeof props.brightness === 'number' ? ' · ' + props.brightness + '%' : ''}</span><span data-active={props.fanOn}>风扇 · {props.fanOn === undefined ? '未知' : props.fanOn ? '运行' : '停止'}</span></div>
    <div className="scene-note"><ScanLine size={13} /><span>拖动旋转 · 双指缩放</span><span>{props.doorActuatorOnly ? '门为执行器反馈' : '状态来自设备上报'}{!props.windowAvailable ? ' · 装饰窗未接设备' : ''}</span></div>
  </div>;
}
