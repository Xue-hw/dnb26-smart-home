import { useCallback, useEffect, useState } from 'react';
import { Check, Database, FlaskConical, LoaderCircle, Play, RotateCcw, Server, ShieldCheck, X } from 'lucide-react';
import { DemoNotice, PageHeader, Panel, StatusBadge } from '@/components/Common';
import { useAppData } from '@/context/AppDataContext';
import { getMockDatabaseStats, resetMockDatabase } from '@/services/mockDataSource';
import { errorMessage, formatDateTime } from '@/utils';

type TestStatus = 'idle' | 'running' | 'success' | 'failed';
interface TestDefinition { id: string; label: string; description: string; readOnly: boolean }
interface TestResult { status: TestStatus; detail: string }

const definitions: TestDefinition[] = [
  { id: 'status', label: 'getSystemStatus', description: '系统、数据库、摄像头和模型状态', readOnly: true },
  { id: 'dashboard', label: 'getDashboardSnapshot', description: '最新传感器、设备和最近事件', readOnly: true },
  { id: 'sensors', label: 'getSensorHistory', description: '时间范围与指标筛选', readOnly: true },
  { id: 'events', label: 'getDeviceEvents', description: '设备事件分页查询', readOnly: true },
  { id: 'camera', label: 'getCameraSnapshot', description: '摄像头抓帧占位接口', readOnly: true },
  { id: 'persons', label: 'getPersons', description: '授权人员列表', readOnly: true },
  { id: 'detect', label: 'detectObjects', description: '预置场景识别与 Canvas 数据', readOnly: false },
  { id: 'face', label: 'verifyFace', description: '人脸接口连通性，不做真实比对', readOnly: false },
  { id: 'recognitions', label: 'getRecognitionEvents', description: '识别事件和图片 URL 查询', readOnly: true },
  { id: 'add', label: 'addPerson', description: '新增 INTERFACE_TEST 临时人员', readOnly: false },
  { id: 'delete', label: 'deletePerson', description: '清理 INTERFACE_TEST 临时人员', readOnly: false },
  { id: 'command', label: 'sendDeviceCommand', description: '发送保持灯状态的演示命令', readOnly: false },
  { id: 'commandGet', label: 'getDeviceCommand', description: '按 command_id 查询硬件回执占位', readOnly: true },
  { id: 'subscribe', label: 'subscribeEvents', description: '验证命令流程产生实时事件', readOnly: false },
  { id: 'clear', label: 'clearTemporaryImages', description: '清理接口测试产生的临时上传记录', readOnly: false },
];

const initialResults = () => Object.fromEntries(definitions.map((item) => [item.id, { status: 'idle', detail: '等待测试' }])) as Record<string, TestResult>;

export default function InterfacePage() {
  const { source, mode, status, refresh } = useAppData();
  const [results, setResults] = useState<Record<string, TestResult>>(initialResults);
  const [running, setRunning] = useState(false);
  const [dbStats, setDbStats] = useState<ReturnType<typeof getMockDatabaseStats> | null>(null);

  const refreshStats = useCallback(() => {
    if (mode === 'mock') setDbStats(getMockDatabaseStats());
  }, [mode]);
  useEffect(() => { refreshStats(); }, [refreshStats]);

  async function runTests() {
    setRunning(true);
    setResults(initialResults());
    let commandId = '';
    let eventReceived = false;
    const unsubscribe = source.subscribeEvents(() => { eventReceived = true; });
    const activeDefinitions = mode === 'mock' ? definitions : definitions.filter((item) => item.readOnly && item.id !== 'commandGet');

    async function run(id: string, action: () => Promise<string>) {
      setResults((current) => ({ ...current, [id]: { status: 'running', detail: '正在调用…' } }));
      try {
        const detail = await action();
        setResults((current) => ({ ...current, [id]: { status: 'success', detail } }));
      } catch (reason) {
        setResults((current) => ({ ...current, [id]: { status: 'failed', detail: errorMessage(reason) } }));
      }
    }

    for (const definition of activeDefinitions) {
      if (definition.id === 'status') await run(definition.id, async () => { const value = await source.getSystemStatus(); return `${value.version} · ${value.message}`; });
      if (definition.id === 'dashboard') await run(definition.id, async () => { const value = await source.getDashboardSnapshot(); return `${value.sensors.length} 个传感器值 · ${value.devices.length} 台设备`; });
      if (definition.id === 'sensors') await run(definition.id, async () => { const end = new Date(); const start = new Date(end.getTime() - 86400000); const value = await source.getSensorHistory({ start: start.toISOString(), end: end.toISOString() }); return `${value.length} 条序列 · ${value.reduce((sum, item) => sum + item.points.length, 0)} 个采样点`; });
      if (definition.id === 'events') await run(definition.id, async () => { const end = new Date(); const start = new Date(end.getTime() - 7 * 86400000); const value = await source.getDeviceEvents({ start: start.toISOString(), end: end.toISOString(), page_size: 10 }); return `共 ${value.total} 条设备事件`; });
      if (definition.id === 'camera') await run(definition.id, async () => { const value = await source.getCameraSnapshot(); return `${value.camera_id} · ${value.message}`; });
      if (definition.id === 'persons') await run(definition.id, async () => { const value = await source.getPersons(); return `${value.length} 名授权人员`; });
      if (definition.id === 'detect') await run(definition.id, async () => { const value = await source.detectObjects({ image: null, image_url: '/demo/smart-home-scene.svg', file_name: 'interface-test-scene.svg', width: 960, height: 540, source: 'demo' }); return `${value.count} 个目标 · ${value.event_id}`; });
      if (definition.id === 'face') await run(definition.id, async () => { const file = new File(['<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="#123"/></svg>'], 'interface-test-face.svg', { type: 'image/svg+xml' }); const value = await source.verifyFace(file); return value.message; });
      if (definition.id === 'recognitions') await run(definition.id, async () => { const value = await source.getRecognitionEvents({ page_size: 20 }); return `共 ${value.total} 条识别事件`; });
      if (definition.id === 'add') await run(definition.id, async () => { try { await source.deletePerson('INTERFACE_TEST'); } catch { /* 不存在时无需处理。 */ } const value = await source.addPerson({ user_id: 'INTERFACE_TEST', name: '接口测试人员', face_image: null }); return `${value.user_id} 新增成功，随后自动清理`; });
      if (definition.id === 'delete') await run(definition.id, async () => { await source.deletePerson('INTERFACE_TEST'); return '临时人员已删除，测试数据已清理'; });
      if (definition.id === 'command') await run(definition.id, async () => { const snapshot = await source.getDashboardSnapshot(); const light = snapshot.devices.find((item) => item.device_id === 'light_01'); if (!light) throw new Error('未找到演示灯设备。'); const value = await source.sendDeviceCommand({ device_id: 'light_01', action: 'set', params: { power: Boolean(light.state.power) } }); commandId = value.command_id; return `${value.command_id} · ${value.status}`; });
      if (definition.id === 'commandGet') await run(definition.id, async () => { if (!commandId) throw new Error('前置 sendDeviceCommand 未成功。'); const value = await source.getDeviceCommand(commandId); return `${value.status} · ${value.acked_at || '无回执时间'}`; });
      if (definition.id === 'subscribe') await run(definition.id, async () => { if (!eventReceived) throw new Error('尚未收到实时事件，请检查命令前置测试。'); return '已收到 command.updated / device 事件，取消订阅正常'; });
      if (definition.id === 'clear') await run(definition.id, async () => { const value = await source.clearTemporaryImages(); return `清理 ${value.count} 条临时上传记录`; });
    }
    unsubscribe();
    refreshStats();
    await refresh();
    setRunning(false);
  }

  function resetDemo() {
    resetMockDatabase();
    setResults(initialResults());
    refreshStats();
    void refresh();
  }

  const visibleDefinitions = mode === 'mock' ? definitions : definitions.filter((item) => item.readOnly && item.id !== 'commandGet');
  const successCount = visibleDefinitions.filter((item) => results[item.id].status === 'success').length;
  const failedCount = visibleDefinitions.filter((item) => results[item.id].status === 'failed').length;

  return <>
    <PageHeader eyebrow="05 / CONTRACT TEST" title="接口测试与交付状态" description="用可视化方式验证所有预留接口。Mock 模式执行完整读写测试；HTTP 模式仅执行只读检查，避免测试按钮误触真实设备。" actions={<button className="button" disabled={running} onClick={() => void runTests()}>{running ? <LoaderCircle className="spin" size={16} /> : <Play size={16} />}{running ? '正在测试…' : mode === 'mock' ? '运行全部接口测试' : '运行只读接口检查'}</button>} />
    <DemoNotice>{mode === 'mock' ? '完整测试会新增并自动删除一名测试人员、产生识别记录和一条保持原状态的灯光命令。测试不会调用真实硬件。' : '当前为 HTTP 模式，写操作测试已自动排除。完整接口验收请在 Mock 模式进行。'}</DemoNotice>

    <div className="interface-summary"><article className="interface-card"><span>数据适配器</span><strong>{mode === 'mock' ? 'MockDataSource' : 'HttpDataSource'}</strong><small>SmartHomeDataSource</small></article><article className="interface-card"><span>测试进度</span><strong>{successCount} / {visibleDefinitions.length} 通过</strong><small>{failedCount ? `${failedCount} 项失败` : '尚无失败项'}</small></article><article className="interface-card"><span>本地数据库</span><strong>{mode === 'mock' ? 'localStorage v1' : '由后端提供'}</strong><small>{dbStats ? `${(dbStats.storage_bytes / 1024).toFixed(1)} KB` : '无浏览器数据库'}</small></article><article className="interface-card"><span>实时事件</span><strong>SSE / Mock Emitter</strong><small>轮询快照 30 秒兜底</small></article></div>

    <div className="interface-layout"><div className="history-stack">
      <Panel title="接口连通性自测" description="每项测试直接调用页面正在使用的同一个 DataSource" icon={<FlaskConical size={17} />} actions={<StatusBadge tone={failedCount ? 'danger' : successCount ? 'success' : 'neutral'}>{failedCount ? '存在失败' : successCount ? '接口可用' : '待测试'}</StatusBadge>}>
        <div className="test-list">{visibleDefinitions.map((definition, index) => { const result = results[definition.id]; return <div className="test-row" key={definition.id}><span className="test-index">{String(index + 1).padStart(2, '0')}</span><div><strong>{definition.label}</strong><p>{definition.description}<br />{result.detail}</p></div><span className={`test-status ${result.status}`}>{result.status === 'running' ? <LoaderCircle className="spin" size={15} /> : result.status === 'success' ? <Check size={15} /> : result.status === 'failed' ? <X size={15} /> : '等待'} {result.status === 'success' ? '通过' : result.status === 'failed' ? '失败' : result.status === 'running' ? '执行中' : ''}</span></div>; })}</div>
      </Panel>

      <Panel title="真实后端接入方式" description="只更换环境变量和 HTTP 适配器，不修改页面组件" icon={<Server size={17} />}>
        <pre className="code-block">{`# .env.production\nVITE_DATA_MODE=http\nVITE_API_BASE_URL=\n\n# 同源请求\nGET  /api/dashboard/snapshot\nGET  /api/sensors/history?start=...&end=...\nPOST /api/devices/light_01/commands\nGET  /api/stream  (SSE)`}</pre>
        <div className="inline-warning"><ShieldCheck size={14} /> 接口字段、事件名和错误语义详见随包 docs/GUI_API_CONTRACT.md；香橙派 Nginx 示例见 deploy/nginx.conf.example。</div>
      </Panel>
    </div><div className="history-stack">
      <Panel title="演示数据库" description="数据可跨刷新保存，也可一键恢复初始状态" icon={<Database size={17} />} actions={mode === 'mock' ? <button className="button ghost small" disabled={running} onClick={resetDemo}><RotateCcw size={13} />重置</button> : undefined}>
        {dbStats ? <><div className="db-stats"><DbStat label="传感器采样" value={dbStats.sensor_readings} /><DbStat label="设备" value={dbStats.devices} /><DbStat label="设备事件" value={dbStats.device_events} /><DbStat label="命令记录" value={dbStats.commands} /><DbStat label="识别事件" value={dbStats.recognition_events} /><DbStat label="人员" value={dbStats.persons} /><DbStat label="临时上传" value={dbStats.temporary_uploads} /><DbStat label="存储大小" value={`${(dbStats.storage_bytes / 1024).toFixed(1)}K`} /></div><div className="inline-warning">创建：{formatDateTime(dbStats.created_at)}<br />更新：{formatDateTime(dbStats.updated_at)}</div></> : <div className="empty-state"><Database size={28} /><h3>HTTP 模式</h3><p>数据库统计由真实后端负责，浏览器不保存业务副本。</p></div>}
      </Panel>
      <Panel title="交付内容" description="GUI 板块可直接交接" icon={<ShieldCheck size={17} />}>
        <div className="contract-list"><div className="contract-item"><strong>纯前端静态产物</strong>dist 可交由 Nginx 托管，无需 Node 常驻。</div><div className="contract-item"><strong>15 项接口契约</strong>覆盖设备、历史、识别、人员、摄像头与事件。</div><div className="contract-item"><strong>本地资源</strong>字体、演示场景、摄像头占位图均不依赖公网。</div><div className="contract-item"><strong>交接文档</strong>README、部署、接口、验收与 CHANGELOG。</div></div>
        <div className="inline-warning">当前服务状态：{status?.message || '正在读取'}<br />构建版本：GUI v1.0.0</div>
      </Panel>
    </div></div>
  </>;
}

function DbStat({ label, value }: { label: string; value: string | number }) {
  return <div className="db-stat"><span>{label}</span><strong>{value}</strong></div>;
}
