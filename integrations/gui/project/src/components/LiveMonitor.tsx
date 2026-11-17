import { useCallback, useEffect, useState } from 'react';
import { LiveVideo } from './LiveVideo';
import { RecognitionLegend } from './RecognitionLegend';
import { faceStyle, objectStyle } from '@/services/recognitionStyles';
import { Camera, RefreshCw } from 'lucide-react';
import { useAppData } from '@/context/AppDataContext';
import { backendUrl } from '@/services/connection';
import { faceAccessLabel } from '@/services/facePolicy';
import { captureIsFresh } from '@/services/liveFreshness';
import { isHardwareSimulation } from '@/services/hardwarePolicy';
import type { DeviceCommand, FaceCooldown, LiveVision } from '@/types/contracts';
import { errorMessage, formatDateTime } from '@/utils';
import { ErrorState, Panel, StatusBadge } from './Common';

export function LiveMonitor() {
  const { source, mode } = useAppData();
  const [sample, setSample] = useState<{ source: typeof source; live: LiveVision; receivedAt: number; requestDuration: number } | null>(null);
  const [lastCooldown, setLastCooldown] = useState<{ source: typeof source; value: FaceCooldown } | null>(null);
  const [error, setError] = useState('');
  const [streamError, setStreamError] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const videoFailed = useCallback(() => setStreamError(true), []);
  const videoReady = useCallback(() => setStreamError(false), []);
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(performance.now()), 1000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    async function poll() {
      const started = performance.now();
      try {
        const live = await source.getLiveVision();
        const receivedAt = performance.now();
        if (!cancelled) {
          setSample({ source, live, receivedAt, requestDuration: receivedAt - started });
          setLastCooldown({ source, value: live.face_cooldown ?? { active: false, phase: 'idle', command_id: null } });
          setNow(receivedAt); setError('');
        }
      }
      catch (reason) { if (!cancelled) { setError(errorMessage(reason)); setSample(null); } }
      finally { if (!cancelled) timer = window.setTimeout(() => void poll(), 1000); }
    }
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [source]);
  const live = sample?.source === source ? sample.live : undefined;
  const cooldown = lastCooldown?.source === source ? lastCooldown.value : undefined;
  const cameraOnline = !error && live?.camera_status === 'online';
  const fresh = Boolean(cameraOnline && sample && captureIsFresh(live?.captured_at, live?.server_time, sample.receivedAt, now, sample.requestDuration));
  const faceFresh = Boolean(cameraOnline && sample && captureIsFresh(live?.face_captured_at, live?.server_time, sample.receivedAt, now, sample.requestDuration));
  return <Panel title="共享实时摄像头" description="YOLO 与人脸服务共享板端输入。静态上传不会产生眨眼通行资格。" icon={<Camera size={18} />} actions={<StatusBadge tone={mode === 'mock' || !fresh ? 'warning' : 'success'}>{mode === 'mock' ? '模拟模式 · 无真实活体' : fresh ? '实时输入' : '画面不可用或已过期'}</StatusBadge>}>
    {error && <ErrorState message={error} />}
    <RecognitionLegend />
    <div className="monitor-grid"><div><div className="preview-frame live-preview">{mode === 'http' && fresh ? <LiveVideo key={streamKey} src={backendUrl(`/api/camera/stream?view=${streamKey}`)} onError={videoFailed} onReady={videoReady} /> : <div className="preview-placeholder"><Camera size={40} /><h3>{mode === 'mock' ? '演示模式没有实时摄像头' : '等待摄像头恢复'}</h3><p>{live?.message || '未收到新鲜画面，不显示旧的通行结果。'}</p></div>}</div>{streamError && <ErrorState message="实时视频连接失败，请检查摄像头和代理配置。" />}<button className="button secondary small" onClick={() => { setStreamError(false); setStreamKey(key => key + 1); }}><RefreshCw size={14} />重新连接画面</button><p className="form-help">帧 {live?.frame_id ?? '—'} · {formatDateTime(live?.captured_at || undefined)}{typeof live?.inference_ms === 'number' && ` · 推理 ${live.inference_ms.toFixed(0)} ms`}</p></div>
    <div aria-live="polite"><h3>物体识别</h3>{fresh && live?.objects?.length ? live.objects.map((object, index) => <p key={`${object.label}-${index}`} style={{ borderLeft: `4px solid ${objectStyle(object).color}`, paddingLeft: 8 }}>{objectStyle(object).label} · {object.label_zh || object.label} · {(object.confidence * 100).toFixed(1)}%</p>) : <p className="form-help">{fresh ? '当前帧没有目标' : '等待有效识别结果'}</p>}<h3>人脸与通行判定</h3>{cooldown?.active ? <div className="face-cooldown" role="status"><StatusBadge tone="warning">通行冷却中</StatusBadge><p>{cooldown.phase === 'waiting_open' ? '等待入户门开门反馈' : cooldown.phase === 'unknown' ? '开门结果待确认，等待门状态反馈' : '等待入户门关闭反馈'}</p><p className="form-help">冷却期间暂停人脸验证，收到本轮关闭反馈后恢复。</p>{error && <p className="form-help">连接中断，保留上次冷却状态，等待后端确认。</p>}{cooldown.command_id && <CommandReceipt key={cooldown.command_id} commandId={cooldown.command_id} />}</div> : faceFresh && live?.faces?.length ? live.faces.map((face, index) => <article className="live-face" key={`${face.user_id}-${index}`} style={{ borderLeft: `4px solid ${faceStyle(face).color}`, paddingLeft: 8 }}><strong>{face.identity_recheck && face.liveness_status === 'pending' ? '活体验证中' : face.user_name || '未授权人员'}</strong>{!(face.identity_recheck && face.liveness_status === 'pending') && <p>{faceStyle(face).label}</p>}<StatusBadge tone={face.identity_matched && face.access_granted && face.liveness_status === 'passed' ? 'success' : 'warning'}>{faceAccessLabel({ matched: face.identity_matched, access_granted: face.access_granted, liveness_status: face.liveness_status, identity_recheck: face.identity_recheck, verification_remaining_seconds: face.verification_remaining_seconds }, 'camera')}</StatusBadge>{typeof face.similarity === 'number' && Number.isFinite(face.similarity) && <p>当前匹配分数：{(face.similarity * 100).toFixed(1)}%{typeof face.match_threshold === 'number' && Number.isFinite(face.match_threshold) ? ` · 门限：${(face.match_threshold * 100).toFixed(1)}%` : ''}</p>}{face.reason && <p>{face.reason}</p>}{face.command_id && <CommandReceipt key={face.command_id} commandId={face.command_id} />}</article>) : <p className="form-help">{faceFresh ? '当前画面未检测到人脸' : '人脸输入异常或结果已过期，不保留通过提示'}</p>}</div></div>
  </Panel>;
}

function CommandReceipt({ commandId }: { commandId: string }) {
  const { source, mode, status, snapshot } = useAppData();
  const [command, setCommand] = useState<DeviceCommand | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    async function poll() {
      try {
        const next = await source.getDeviceCommand(commandId);
        if (cancelled) return;
        setCommand(next); setError('');
        if (next.status === 'pending') timer = window.setTimeout(() => void poll(), 1000);
      } catch (reason) { if (!cancelled) setError(errorMessage(reason)); }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [source, commandId]);
  const current = command?.command_id === commandId ? command : null;
  const simulated = isHardwareSimulation(mode, status, snapshot) || current?.source === 'mock';
  const labels = { pending: simulated ? '模拟开门申请已提交，等待模拟回执' : '开门申请已提交，等待控制器回执', acked: simulated ? '模拟回执已确认；Arduino 尚未接入，不代表实际开门' : '控制器已确认执行；物理门状态以传感器为准', failed: '控制命令失败', timeout: '控制确认超时，结果未知' };
  return <div className="form-help">关联命令：{commandId}<p>{error ? `无法查询执行结果：${error}` : current ? labels[current.status] || '执行状态未知' : '正在查询执行回执…'}</p>{current?.error_message && <p>{current.error_message}</p>}</div>;
}
