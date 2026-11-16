import { NavLink } from 'react-router-dom';
import { SystemAlerts } from '@/components/SystemAlerts';
import { HardwareBoards } from '@/components/HardwareBoards';
import { DeviceExtras } from '@/components/DeviceExtras';
import { useEffect, useState } from 'react';
import { AirVent, DoorOpen, Droplets, LockKeyhole, Square, Fan, Home, Lightbulb, Power, RefreshCw, Thermometer } from 'lucide-react';
import { DemoNotice, EmptyState, ErrorState, LoadingBlock, PageHeader, Panel, StatusBadge } from '@/components/Common';
import { HouseModel } from '@/components/HouseModel';
import { useAppData } from '@/context/AppDataContext';
import { isHardwareSimulation } from '@/services/hardwarePolicy';
import type { DeviceState } from '@/types/contracts';
import { deviceAction, deviceStateText, deviceEventActionText, errorMessage, formatDateTime, positionText } from '@/utils';

export default function DashboardPage() {
  const { source, snapshot, status, mode, loading, error, connectionError, pendingCommands, refresh, sendCommand } = useAppData();
  const simulatedHardware = isHardwareSimulation(mode, status, snapshot);
  const [filter, setFilter] = useState('全部');
  const [draft, setDraft] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const [writeAccess, setWriteAccess] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void source.getAuthStatus().then(result => { if (!cancelled) setWriteAccess(result.write_access); }).catch(() => { if (!cancelled) setWriteAccess(false); });
    return () => { cancelled = true; };
  }, [source]);
  const devices = snapshot?.devices || [];
  const visibleDevices = devices.filter(d => filter === '全部' || (filter === '照明' ? d.kind === 'light' : filter === '环境' ? ['fan', 'air_conditioner'].includes(d.kind) : ['door', 'window', 'lock'].includes(d.kind)));
  const icons = { light: Lightbulb, fan: Fan, air_conditioner: AirVent, door: DoorOpen, window: Square, lock: LockKeyhole };
  const find = (kind: DeviceState['kind']) => devices.find(d => d.kind === kind);
  const door = devices.find(d => d.kind === 'door' && d.device_id !== 'garage_door'), garage = devices.find(d => d.device_id === 'garage_door'), windowDevice = find('window'), light = find('light'), fan = find('fan');
  const temperature = snapshot?.sensors.find(s => s.metric === 'temperature');
  const humidity = snapshot?.sensors.find(s => s.metric === 'humidity');
  const available = (d?: DeviceState) => d?.status === 'online' && (!d.board_id || status?.hardware_boards?.[d.board_id]?.status === 'online');
  const positionSummary = (d?: DeviceState) => d && !available(d) ? '离线／未确认' : positionText(d);
  const position = (d?: DeviceState) => available(d) && ['open', 'closed'].includes(String(d?.state.position)) ? d?.state.position === 'open' : undefined;
  const power = (d?: DeviceState) => available(d) && typeof d?.state.power === 'boolean' ? d.state.power : undefined;
  const confirmed = typeof light?.state.brightness === 'number' ? light.state.brightness : 0;
  const known = (d: DeviceState) => d.kind === 'door' || d.kind === 'window' ? ['open', 'closed'].includes(String(d.state.position)) : typeof d.state[d.kind === 'lock' ? 'locked' : 'power'] === 'boolean';
  const unavailable = (d: DeviceState) => !writeAccess || (mode === 'http' && !navigator.onLine) || !available(d) || Boolean(pendingCommands[d.device_id]) || Boolean(connectionError) || snapshot?.freshness === 'cached';
  const disabled = (d: DeviceState) => unavailable(d) || !known(d);
  const supports = (d: DeviceState, capability: string) => d.capabilities ? d.capabilities.includes(capability) : capability !== 'mode';
  async function execute(device: DeviceState, params?: Record<string, boolean | number | string>) {
    setMessage(`${device.name}：${simulatedHardware ? '模拟指令已发送，等待模拟回执…' : '指令已发送，等待设备确认…'}`);
    try {
      const command = await sendCommand({ device_id: device.device_id, action: params ? 'set' : 'toggle', params: params || {} });
      setMessage(`${device.name}：${simulatedHardware || command.source === 'mock' ? '模拟回执已确认；Arduino 尚未接入。' : '设备已确认执行；实际位置请现场确认。'}`);
      return true;
    } catch (reason) { setMessage(params && 'pin' in params ? '修改设备 PIN 失败，请检查权限、连接和控制器回执。' : errorMessage(reason)); return false; }
    finally { if (device.kind === 'light') setDraft(null); }
  }
  if (loading && !snapshot) return <LoadingBlock label="正在读取家居状态…" />;
  return <>
    <PageHeader eyebrow="HOME / 01" title="家居总览" description="环境、门禁与照明" actions={<button className="button secondary" onClick={() => void refresh()}><RefreshCw size={16} />刷新状态</button>} />
    <DemoNotice>当前为演示模式，数据和控制结果均为模拟。真实设备尚未接入。</DemoNotice>
    {error && <ErrorState message={error} />}
    {!writeAccess && <p className="inline-warning" role="status">当前控制权限未确认或为只读；请在系统页设置管理员令牌。</p>}
    {message && <div className="result-summary" role="status">{message}</div>}
    <div className="home-hero"><div className="hero-stats"><strong>{devices.filter(available).length}<small> / {devices.length}</small></strong><span>{simulatedHardware ? '可用模拟设备' : '报告在线的设备'}</span><span className="hero-dot">{simulatedHardware ? '硬件模拟空间' : '已连接空间'}</span></div></div>
    <div className="kpi-grid">
      <Card title="室内温度" value={temperature?.status === 'online' ? `${temperature.value} °C` : '待接入'} note={`采样时间 · ${formatDateTime(temperature?.measured_at)}`} icon={<Thermometer />} />
      <Card title="室内湿度" value={humidity?.status === 'online' ? `${humidity.value} %` : '待接入'} note={`相对湿度 · ${formatDateTime(humidity?.measured_at)}`} icon={<Droplets />} />
      <Card title="入户门" value={positionSummary(door)} note={garage ? `车库门：${positionSummary(garage)}` : windowDevice ? `窗户：${positionSummary(windowDevice)}` : '未接入其他门窗设备'} icon={<Home />} />
      <Card title="灯光" value={power(light) === undefined ? '未知' : power(light) ? '已开启' : '已关闭'} note={light && !supports(light, 'brightness') ? '仅开关控制' : available(light) && typeof light?.state.brightness === 'number' ? `设备亮度 ${confirmed}%` : '亮度待同步'} icon={<Lightbulb />} />
      <Card title="风扇" value={power(fan) === undefined ? '未知' : power(fan) ? '运行中' : '已关闭'} note="自动温控配置见系统页；运行以设备反馈为准" icon={<Fan />} />
    </div>
    <div className="dashboard-grid">
      <Panel title="空间视图" description="模型随设备反馈更新" icon={<Home size={18} />}>
        <div className="house-scene"><HouseModel doorOpen={position(door)} garagePosition={available(garage) ? String(garage?.state.position) : undefined} lightColor={typeof light?.state.color === 'string' ? light.state.color : undefined} windowOpen={position(windowDevice)} windowAvailable={Boolean(windowDevice)} doorActuatorOnly={door?.state.state_basis === 'actuator'} fanOn={power(fan)} lightOn={power(light)} brightness={light && supports(light, 'brightness') && available(light) && typeof light.state.brightness === 'number' ? light.state.brightness : undefined} temperature={temperature?.status === 'online' ? temperature.value : undefined} humidity={humidity?.status === 'online' ? humidity.value : undefined} /><div className="scene-caption">快照时间：{formatDateTime(snapshot?.server_time)}</div></div>
      </Panel>
      <Panel title="设备控制" description="操作后等待设备确认；离线设备不可控制。" icon={<Power size={18} />}>
        <div className="device-filters" role="group" aria-label="设备分类">{['全部', '照明', '环境', '门窗'].map(f => <button key={f} aria-pressed={filter === f} className={filter === f ? 'device-filter active' : 'device-filter'} onClick={() => setFilter(f)}>{f}</button>)}</div><div className="control-list">{visibleDevices.map(d => { const Icon = icons[d.kind]; return <div className={`control-row ${d.state.power === true || d.state.position === 'open' ? 'device-active' : ''}`} key={d.device_id}><span className="device-icon"><Icon size={23} /></span><div className="control-info"><div><strong>{d.name}</strong><small>{d.board_id && `${d.board_id.toUpperCase()} · `}{available(d) ? deviceStateText(d.state) || '状态未知' : '状态不可用'}</small></div></div><div className="control-actions"><StatusBadge tone={available(d) ? 'success' : 'warning'}>{available(d) ? simulatedHardware ? '模拟' : '在线' : d.status === 'offline' ? '离线' : '未知'}</StatusBadge><button className="button secondary small" disabled={disabled(d)} onClick={() => void execute(d)}>{pendingCommands[d.device_id] ? '等待确认…' : d.state.position === 'moving' ? '移动中' : !known(d) ? '状态未知' : deviceAction(d)}</button>{['light', 'fan'].includes(d.kind) && supports(d, 'mode') && <button className="button secondary small" aria-label={`${d.name}恢复自动`} disabled={unavailable(d) || d.state.mode === 'auto'} onClick={() => void execute(d, { mode: 'auto' })}>恢复自动</button>}{d.kind === 'air_conditioner' && typeof d.state.target_temperature === 'number' && <><button className="button secondary small" aria-label="降低空调设定温度" disabled={disabled(d) || d.state.target_temperature <= 16} onClick={() => void execute(d, { target_temperature: Number(d.state.target_temperature) - 1 })}>−</button><button className="button secondary small" aria-label="提高空调设定温度" disabled={disabled(d) || d.state.target_temperature >= 30} onClick={() => void execute(d, { target_temperature: Number(d.state.target_temperature) + 1 })}>＋</button></>}</div><DeviceExtras device={d} disabled={unavailable(d)} execute={params => execute(d, params)} /></div>; })}</div>
        {!visibleDevices.length && <EmptyState title="该分类暂无设备" description="选择其他分类或等待设备接入。" />}
        {light && supports(light, 'brightness') && <div className="range-row"><div className="range-label"><span>目标亮度</span><strong>{draft ?? confirmed}%</strong></div><input aria-label="目标灯光亮度" type="range" min="0" max="100" value={draft ?? confirmed} disabled={disabled(light)} onChange={e => setDraft(Number(e.target.value))} /><p className="form-help">{simulatedHardware ? '模拟亮度' : '设备已确认'}：{typeof light.state.brightness === 'number' ? `${confirmed}%` : '未知'}。调整后点击应用。</p><button className="button" disabled={disabled(light) || draft === null} onClick={() => void execute(light, { brightness: draft ?? confirmed })}>{pendingCommands[light.device_id] ? '正在设置…' : '应用亮度'}</button></div>}
      </Panel>
    </div>
    <SystemAlerts compact />
    <HardwareBoards boards={status?.hardware_boards} simulated={simulatedHardware} />
    <div className="sensor-strip">{snapshot?.sensors.filter(sensor => !['temperature', 'humidity'].includes(sensor.metric)).map(sensor => <article className="kpi-card" key={sensor.id}><strong>{{smoke: '烟雾', rain: '雨滴', light: '光照'}[sensor.metric as 'smoke' | 'rain' | 'light'] || sensor.metric}</strong><p>{sensor.status === 'online' ? `${sensor.value} ${sensor.unit}` : '未知／未接入'}</p><small>{formatDateTime(sensor.measured_at)}</small></article>)}</div>
    <div className="integration-grid">
      <Panel title="自动温控" description="温度过高时，由硬件或后端自动启动风扇。"><StatusBadge tone="info">配置与状态分开管理</StatusBadge><p className="integration-copy">UNO1 本地执行自动温控。手动开关或亮度操作会切换手动模式；点击恢复自动交还控制。语音临时操作 5 秒后恢复此前模式与设置。温控阈值的硬件确认状态见系统页。</p><NavLink to="/system" className="button secondary">查看系统与联动配置</NavLink></Panel>
      <Panel title="门禁核验" description="授权身份与实际开门结果分别展示。"><StatusBadge tone="info">身份、活体、门状态分别展示</StatusBadge><p className="integration-copy">查看实时画面与识别结果。身份、眨眼和开门回执分别记录。</p></Panel>
    </div>
    <Panel title="最近活动" description="记录设备状态变化与控制操作。">{snapshot?.recent_events.length ? <div className="event-list">{snapshot.recent_events.map(e => <div className="event-item" key={e.event_id}><span className="event-marker" /><div><strong>{e.device_name}</strong><p>{[deviceEventActionText(e), deviceStateText(e.state)].filter(Boolean).join(' · ')}</p></div><span className="event-time">{formatDateTime(e.occurred_at)}</span></div>)}</div> : <EmptyState title="暂无活动" description="设备状态变化后会显示在这里。" />}</Panel>
  </>;
}
function Card({ title, value, note, icon }: { title: string; value: string; note: string; icon: React.ReactNode }) {
  return <article className="kpi-card"><div className="kpi-top"><span>{title}</span>{icon}</div><div className="kpi-value">{value}</div><div className="kpi-meta">{note}</div></article>;
}
