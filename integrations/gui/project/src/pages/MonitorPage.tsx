import { LiveMonitor } from '@/components/LiveMonitor';
import { faceAccessLabel } from '@/services/facePolicy';
import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import { Camera, CheckCircle2, FileImage, Image as ImageIcon, LoaderCircle, Play, ScanFace, ScanSearch, ShieldAlert, Upload, Video } from 'lucide-react';
import { DemoNotice, EmptyState, ErrorState, PageHeader, Panel, StatusBadge } from '@/components/Common';
import { DetectionCanvas } from '@/components/DetectionCanvas';
import { useAppData } from '@/context/AppDataContext';
import type { Detection, DetectionResult, FaceVerifyResult, RecognitionEvent, RecognitionSource, CameraSnapshot } from '@/types/contracts';
import { errorMessage, formatDateTime } from '@/utils';
import { loadMediaImage } from '@/services/mediaImage';
import { objectStyle } from '@/services/recognitionStyles';

type SourceTab = 'demo' | 'upload' | 'camera';
const noDetections: Detection[] = [];

export default function MonitorPage() {
  const { source, mode } = useAppData();
  const [tab, setTab] = useState<SourceTab>(mode === 'mock' ? 'demo' : 'upload');
  const [imageUrl, setImageUrl] = useState(mode === 'mock' ? '/demo/smart-home-scene.svg' : '');
  const [fileName, setFileName] = useState(mode === 'mock' ? 'smart-home-scene.svg' : '');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [detectionResult, setDetectionResult] = useState<DetectionResult | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState('');
  const [recent, setRecent] = useState<RecognitionEvent[]>([]);
  const [cameraSnapshot, setCameraSnapshot] = useState<CameraSnapshot | null>(null);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraMessage, setCameraMessage] = useState('');
  const [facePreview, setFacePreview] = useState('');
  const [faceFile, setFaceFile] = useState<File | null>(null);
  const [faceResult, setFaceResult] = useState<FaceVerifyResult | null>(null);
  const [faceLoading, setFaceLoading] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);
  const faceInputRef = useRef<HTMLInputElement>(null);
  const objectUrls = useRef<string[]>([]);
  const detectionAbort = useRef<AbortController | null>(null);
  const faceAnnotations = useMemo(() => (faceResult?.face_boxes || []).map(bbox => ({
    bbox, identity_matched: faceResult?.face_boxes.length === 1 ? (faceResult.identity_matched ?? faceResult.matched) : undefined,
    liveness_status: faceResult?.liveness_status, access_granted: false,
  })), [faceResult]);

  useEffect(() => () => { detectionAbort.current?.abort(); objectUrls.current.forEach((url) => URL.revokeObjectURL(url)); }, []);

  async function refreshRecognition() {
    try {
      const result = await source.getRecognitionEvents({ page: 1, page_size: 20 });
      setRecent(result.items);
    } catch (reason) { setError(errorMessage(reason)); }
  }

  useEffect(() => { void refreshRecognition(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function selectTab(next: SourceTab) {
    if (detecting || cameraLoading) return;
    setTab(next);
    setError('');
    setDetectionResult(null);
    setDetections([]);
    if (next === 'demo') {
      setSelectedFile(null);
      setImageUrl('/demo/smart-home-scene.svg');
      setFileName('smart-home-scene.svg');
      setCameraMessage('');
    }
    if (next === 'upload') {
      setSelectedFile(null);
      setImageUrl('');
      setFileName('');
      setCameraMessage('');
    }
    if (next === 'camera') void loadCamera();
  }

  async function loadCamera() {
    setError(''); setCameraLoading(true); setImageUrl(''); setCameraSnapshot(null); setDetections([]); setDetectionResult(null);
    try {
      const snapshot = await source.getCameraSnapshot();
      setCameraSnapshot(snapshot);
      setSelectedFile(null);
      setImageUrl(snapshot.image_url);
      setFileName(`${snapshot.camera_id}-snapshot`);
      setCameraMessage(snapshot.message);
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setCameraLoading(false); }
  }

  function chooseImage(file?: File) {
    if (!file || detecting || cameraLoading) return;
    if (!file.type.startsWith('image/')) { setError('请选择图片文件。'); return; }
    if (file.size > 8 * 1024 * 1024) { setError('图片不能超过 8 MB。'); return; }
    const url = URL.createObjectURL(file);
    objectUrls.current.push(url);
    setTab('upload');
    setSelectedFile(file);
    setImageUrl(url);
    setFileName(file.name);
    setDetections([]);
    setDetectionResult(null);
    setError('');
  }

  function dropImage(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    if (detecting || cameraLoading) return;
    if (event.dataTransfer.files.length !== 1) { setError('一次只选择一张图片。'); return; }
    chooseImage(event.dataTransfer.files[0]);
  }

  async function runDetection() {
    if (!imageUrl) { setError('请先选择演示场景或上传图片。'); return; }
    const controller = new AbortController();
    detectionAbort.current?.abort();
    detectionAbort.current = controller;
    setDetecting(true);
    setError('');
    let release: (() => void) | undefined;
    try {
      const resource = await loadMediaImage(imageUrl, controller.signal);
      release = resource.release;
      if (controller.signal.aborted) return;
      const image = resource.image;
      const recognitionSource: RecognitionSource = tab === 'camera' ? 'camera' : selectedFile ? 'upload' : 'demo';
      const result = await source.detectObjects({
        image: selectedFile,
        image_url: imageUrl,
        file_name: fileName || 'demo-image',
        width: image.naturalWidth,
        height: image.naturalHeight,
        source: recognitionSource,
      });
      if (controller.signal.aborted) return;
      setDetections(result.detections);
      setDetectionResult(result);
      await refreshRecognition();
    } catch (reason) { if (!controller.signal.aborted) setError(errorMessage(reason)); }
    finally { release?.(); if (!controller.signal.aborted) setDetecting(false); }
  }

  function chooseFace(file?: File) {
    if (!file) return;
    if (!file.type.startsWith('image/')) { setError('人脸验证需要图片文件。'); return; }
    if (file.size > 8 * 1024 * 1024) { setError('人脸图片不能超过8 MB。'); return; }
    const url = URL.createObjectURL(file);
    objectUrls.current.push(url);
    setFaceFile(file);
    setFacePreview(url);
    setFaceResult(null);
    setError('');
  }

  async function runFaceVerify() {
    if (!faceFile) { setError('请先上传人脸测试图片。'); return; }
    setFaceLoading(true);
    setError('');
    try {
      const result = await source.verifyFace(faceFile);
      setFaceResult(result);
      await refreshRecognition();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setFaceLoading(false); }
  }

  return <>
    <PageHeader eyebrow="02 / RECOGNITION" title="监控与识别" description="查看摄像头照片、识别物体和核验通行身份。" actions={<StatusBadge tone={mode === 'mock' ? 'warning' : 'info'}>{mode === 'mock' ? '模拟识别 · 非真实结果' : '后端识别服务'}</StatusBadge>} />
    <DemoNotice>物体识别返回的是与预置场景对应的固定结果，用于测试接口和检测框，不代表上传图片的真实内容。人脸识别仅测试请求与响应，不比对特征、不触发门禁。</DemoNotice>
    {error && <ErrorState message={error} />}

    <LiveMonitor />
    <div style={{ height: 20 }} />
    <Panel title="物体识别" description="选择图片来源，查看目标类别、位置与置信度。" icon={<ScanSearch size={18} />}>
      <div className="source-tabs" role="tablist">{mode === 'mock' && <button className={tab === 'demo' ? 'source-tab active' : 'source-tab'} disabled={detecting || cameraLoading} onClick={() => selectTab('demo')}><ImageIcon size={15} />预置场景</button>}<button className={tab === 'upload' ? 'source-tab active' : 'source-tab'} disabled={detecting || cameraLoading} onClick={() => selectTab('upload')}><Upload size={15} />上传图片</button><button className={tab === 'camera' ? 'source-tab active' : 'source-tab'} disabled={detecting || cameraLoading} onClick={() => selectTab('camera')}><Video size={15} />摄像头照片</button></div>
      <div className="monitor-grid"><div role="group" aria-label="上传识别图片" style={{ outline: dragActive ? '2px dashed var(--accent, #178e78)' : undefined, outlineOffset: 4 }} onDrop={dropImage} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = detecting || cameraLoading ? 'none' : 'copy'; if (!detecting && !cameraLoading) setDragActive(true); }} onDragLeave={event => { if (!(event.relatedTarget instanceof Node) || !event.currentTarget.contains(event.relatedTarget)) setDragActive(false); }}>
        <p className="form-help">将一张图片拖入此区域，或点击“选择图片”；最大 8 MB。</p>
        <div className="upload-zone"><div><p>{tab === 'demo' ? '本地 960 × 540 演示场景' : tab === 'upload' ? '选择需要识别的图片' : '获取摄像头最新照片'}</p><small>{fileName || 'PNG / JPG / WebP，最大 8 MB'}</small></div><div className="upload-actions">{tab === 'upload' && <><input ref={uploadRef} hidden type="file" accept="image/*" disabled={detecting || cameraLoading} onChange={(event) => { chooseImage(event.target.files?.[0]); event.target.value = ''; }} /><button className="button secondary small" disabled={detecting} onClick={() => uploadRef.current?.click()}><FileImage size={14} />选择图片</button></>}{tab === 'camera' && <button className="button secondary small" disabled={cameraLoading || detecting} onClick={() => void loadCamera()}><Camera size={14} />重新抓帧</button>}<button className="button small" disabled={detecting || cameraLoading || !imageUrl} onClick={() => void runDetection()}>{detecting ? <LoaderCircle className="spin" size={14} /> : <Play size={14} />}{detecting ? '正在识别…' : '开始识别'}</button></div></div>
        <div className="preview-frame">{imageUrl ? <DetectionCanvas imageUrl={imageUrl} detections={detections} /> : <div className="preview-placeholder"><ImageIcon size={44} /><h3>尚未选择图片</h3><p>点击“选择图片”后开始识别</p></div>}{detecting && <div className="preview-overlay"><LoaderCircle className="spin" size={20} />正在识别图片…</div>}</div>
        {tab === 'camera' && <div className="archive-status"><strong>{cameraLoading ? '正在获取照片…' : '照片与归档'}</strong><p>拍摄时间：{formatDateTime(cameraSnapshot?.captured_at)}</p><p>保存状态：{cameraSnapshot?.saved === true ? '后端确认已保存' : cameraSnapshot?.saved === false ? '未保存' : '待接入保存回执'}</p>{cameraMessage && <p>{cameraMessage}</p>}{cameraSnapshot?.saved && cameraSnapshot.archive_url && <a className="button secondary" href={cameraSnapshot.archive_url} target="_blank" rel="noreferrer">查看归档照片</a>}</div>}
      </div><div>
        {detectionResult ? <div className="result-summary"><strong><CheckCircle2 size={15} /> 识别完成 · {detectionResult.count} 个目标</strong><p>{detectionResult.message}<br />处理耗时 {detectionResult.inference_ms} ms</p></div> : <div className="demo-notice">识别完成后显示目标列表。演示模式结果仅供展示流程。</div>}
        <div className="result-list">{detections.map((detection) => <div className="result-row" key={`${detection.label}-${detection.bbox.join(',')}`} style={{ borderLeft: `4px solid ${objectStyle(detection).color}`, paddingLeft: 8 }}><div className="result-row-top"><strong>{detection.label_zh} <span className="form-help">{detection.label} · {objectStyle(detection).label}</span></strong><span>{(detection.confidence * 100).toFixed(1)}%</span></div><div className="confidence-track"><div className="confidence-fill" style={{ width: `${detection.confidence * 100}%`, backgroundColor: objectStyle(detection).color }} /></div><details><summary>位置详情</summary><small>像素坐标 [{detection.bbox.join(', ')}]</small></details></div>)}</div>
        {!detectionResult && <EmptyState title="等待识别" description="识别后将在照片中标注目标位置。" />}
      </div></div>
    </Panel>

    <div style={{ height: 20 }} />
    <div className="monitor-grid">
      <Panel title="人脸与门禁核验" description="分别查看身份核验与门禁执行结果。" icon={<ScanFace size={17} />}>
        <div className="upload-zone"><div><p>{faceFile?.name || '上传一张测试图片'}</p><small>请选择清晰的人脸图片，最大8 MB</small></div><div className="upload-actions"><input ref={faceInputRef} hidden type="file" accept="image/*" onChange={(event) => chooseFace(event.target.files?.[0])} /><button className="button secondary small" disabled={faceLoading} onClick={() => faceInputRef.current?.click()}><Upload size={14} />选择图片</button><button className="button small" disabled={faceLoading || !faceFile} onClick={() => void runFaceVerify()}>{faceLoading ? <LoaderCircle className="spin" size={14} /> : <ScanFace size={14} />}开始核验</button></div></div>
        {facePreview ? <div className="preview-frame"><DetectionCanvas imageUrl={facePreview} detections={noDetections} faces={faceAnnotations} />{faceLoading && <div className="preview-overlay"><LoaderCircle className="spin" size={20} />正在核验身份…</div>}</div> : <EmptyState title="未选择人脸图片" description={mode === 'mock' ? '演示模式不会录入人脸。' : '选择照片后提交身份核验。'} />}
        <div className="verification-result"><StatusBadge tone={!faceResult || faceResult.mode === 'mock' ? 'info' : faceResult.matched ? 'success' : 'warning'}>{!faceResult ? '等待核验' : faceResult.mode === 'mock' ? '模拟服务，未完成真实核验' : faceResult.matched ? '身份匹配，但静态照片没有通行资格' : '核验未通过'}</StatusBadge>{faceResult && <p>{faceResult.user_name || '未匹配授权人员'} · {faceResult.message}</p>}<div className="inline-warning"><ShieldAlert size={15} />{faceResult ? faceAccessLabel(faceResult, 'upload') : '照片仅供身份核对；实时通行请在共享摄像头前完成眨眼。'}</div></div>
      </Panel>
      <Panel title="最近识别事件" description="最近5条，更多记录可在历史页查询。" icon={<ScanSearch size={17} />}>
        {recent.length ? <div className="event-list">{recent.slice(0, 5).map((event) => <div className="event-item" key={event.event_id}><span className="event-marker" /><div><strong>{event.type === 'object' ? '物体识别' : '人脸核验'} · {event.file_name}</strong><p>{event.result_summary}</p></div><span className="event-time">{formatDateTime(event.occurred_at).slice(5, 16)}</span></div>)}</div> : <EmptyState title="暂无识别事件" description="完成识别后可在这里查看记录。" />}
        <div className="inline-warning">{mode === 'mock' ? '演示上传照片仅在本页预览，不会长期保存。' : '照片是否归档以服务端保存回执为准。'}</div>
      </Panel>
    </div>
  </>;
}
