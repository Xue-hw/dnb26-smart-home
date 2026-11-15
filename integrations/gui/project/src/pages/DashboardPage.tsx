import { useState } from 'react';
import { AirVent, DoorOpen, LockKeyhole, Square, Fan, Home, Lightbulb, Power, RefreshCw, Thermometer } from 'lucide-react';
import { DemoNotice, EmptyState, ErrorState, LoadingBlock, PageHeader, Panel, StatusBadge } from '@/components/Common';
import { HouseModel } from '@/components/HouseModel';
import { useAppData } from '@/context/AppDataContext';
import type { DeviceState } from '@/types/contracts';
import { deviceAction, deviceStateText, errorMessage, formatDateTime, positionText } from '@/utils';

export default function DashboardPage() {
  const { snapshot, mode, loading, error, connectionError, pendingCommands, refresh, sendCommand } = useAppData();
  const [filter, setFilter] = useState('全部');
  const [draft, setDraft] = useState<number | null>(null);
  const [message, setMessage] = useState('');
  const devices = snapshot?.devices || [];
  const visibleDevices = devices.filter(d => filter === '全部' || (filter === '照明' ? d.kind === 'light' : filter === '环境' ? ['fan', 'air_conditioner'].includes(d.kind) : ['door', 'window', 'lock'].includes(d.kind)));
  const icons = { light: Lightbulb, fan: Fan, air_conditioner: AirVent, door: DoorOpen, window: Square, lock: LockKeyhole };
  const find = (kind: DeviceState['kind']) => devices.find(d => d.kind === kind);
  const door = find('door'), windowDevice = find('window'), light = find('light'), fan = find('fan');
  const temperature = snapshot?.sensors.find(s => s.metric === 'temperature');
  const humidity = snapshot?.sensors.find(s => s.metric === 'humidity');
  const available = (d?: DeviceState) => d?.status === 'online';
  const position = (d?: DeviceState) => available(d) && ['open', 'closed'].includes(String(d?.state.position)) ? d?.state.position === 'open' : undefined;
  const power = (d?: DeviceState) => available(d) && typeof d?.state.power === 'boolean' ? d.state.power : undefined;
  const confirmed = typeof light?.state.brightness === 'number' ? light.state.brightness : 0;
  const known = (d: DeviceState) => d.kind === 'door' || d.kind === 'window' ? ['open', 'closed'].includes(String(d.state.position)) : typeof d.state[d.kind === 'lock' ? 'locked' : 'power'] === 'boolean';
  const disabled = (d: DeviceState) => (mode === 'http' && !navigator.onLine) || !known(d) || !available(d) || Boolean(pendingCommands[d.device_id]) || Boolean(connectionError) || snapshot?.freshness === 'cached';
  async function execute(device: DeviceState, params?: Record<string, boolean | number | string>) {
    setMessage(`${device.name}：指令已发送，等待设备确认…`);
    try {
      await sendCommand({ device_id: device.device_id, action: params ? 'set' : 'toggle', params: params || {} });
      setMessage(`${device.name}：${mode === 'mock' ? '演示' : '设备'}已确认执行。`);
    } catch (reason) { setMessage(errorMessage(reason)); }
    finally { if (device.kind === 'light') setDraft(null); }
  }
  if (loading && !snapshot) return <LoadingBlock label="正在读取家居状态…" />;
  return <>
    <PageHeader eyebrow="YOUR SPACE, CONNECTED / 智慧生活" title="家的状态，一目了然" description="查看环境与设备状态，轻松管理灯光、门窗和风扇。" actions={<button className="button secondary" onClick={() => void refresh()}><RefreshCw size={16} />刷新状态</button>} />
    <DemoNotice>当前为演示模式，数据和控制结果均为模拟。真实设备尚未接入。</DemoNotice>
    {error && <ErrorState message={error} />}
    {message && <div className="result-summary" role="status">{message}</div>}
    <div className="home-hero"><div><span className="hero-eyebrow">MY HOME / 我的家</span><h2>让家的每个变化，<br />都清晰可见。</h2><p>环境感知 · 智能控制 · 安心守护</p></div><div className="hero-stats"><strong>{devices.filter(d => d.status === 'online').length}<small> / {devices.length}</small></strong><span>{mode === 'mock' ? '可用模拟设备' : '报告在线的设备'}</span><span className="hero-dot">{mode === 'mock' ? '演示空间' : '已连接空间'}</span></div></div>
    <div className="kpi-grid">
      <Card title="室内温度" value={temperature?.status === 'online' ? `${temperature.value} °C` : '待接入'} note={`湿度 ${humidity?.status === 'online' ? `${humidity.value} %` : '未知'} · ${formatDateTime(temperature?.measured_at)}`} icon={<Thermometer />} />
      <Card title="入户门" value={positionText(door)} note={`窗户：${positionText(windowDevice)}`} icon={<Home />} />
      <Card title="灯光" value={power(light) === undefined ? '未知' : power(light) ? '已开启' : '已关闭'} note={available(light) && typeof light?.state.brightness === 'number' ? `设备亮度 ${confirmed}%` : '亮度待同步'} icon={<Lightbulb />} />
      <Card title="风扇" value={power(fan) === undefined ? '未知' : power(fan) ? '运行中' : '已关闭'} note="温控联动状态待接入" icon={<Fan />} />
    </div>
    <div className="dashboard-grid">
      <Panel title="全屋设备" description="图示随设备确认后的状态更新；未知状态不代表关闭。" icon={<Home size={18} />}>
        <div className="house-scene"><HouseModel doorOpen={position(door)} windowOpen={position(windowDevice)} fanOn={power(fan)} lightOn={power(light)} brightness={confirmed} temperature={temperature?.status === 'online' ? temperature.value : undefined} humidity={humidity?.status === 'online' ? humidity.value : undefined} /><div className="scene-caption">快照时间：{formatDateTime(snapshot?.server_time)}</div></div>
      </Panel>
      <Panel title="设备控制" description="操作后等待设备确认；离线设备不可控制。" icon={<Power size={18} />}>
        <div className="device-filters" role="group" aria-label="设备分类">{['全部', '照明', '环境', '门窗'].map(f => <button key={f} aria-pressed={filter === f} className={filter === f ? 'device-filter active' : 'device-filter'} onClick={() => setFilter(f)}>{f}</button>)}</div><div className="control-list">{visibleDevices.map(d => { const Icon = icons[d.kind]; return <div className={`control-row ${d.state.power === true || d.state.position === 'open' ? 'device-active' : ''}`} key={d.device_id}><span className="device-icon"><Icon size={23} /></span><div className="control-info"><div><strong>{d.name}</strong><small>{available(d) ? deviceStateText(d.state) || '状态未知' : '状态不可用'}</small></div></div><div className="control-actions"><StatusBadge tone={available(d) ? 'success' : 'warning'}>{available(d) ? mode === 'mock' ? '模拟' : '在线' : d.status === 'offline' ? '离线' : '未知'}</StatusBadge><button className="button secondary small" disabled={disabled(d)} onClick={() => void execute(d)}>{pendingCommands[d.device_id] ? '等待确认…' : !known(d) ? '状态未知' : deviceAction(d)}</button>{d.kind === 'air_conditioner' && typeof d.state.target_temperature === 'number' && <><button className="button secondary small" aria-label="降低空调设定温度" disabled={disabled(d) || d.state.target_temperature <= 16} onClick={() => void execute(d, { target_temperature: Number(d.state.target_temperature) - 1 })}>−</button><button className="button secondary small" aria-label="提高空调设定温度" disabled={disabled(d) || d.state.target_temperature >= 30} onClick={() => void execute(d, { target_temperature: Number(d.state.target_temperature) + 1 })}>＋</button></>}</div></div>; })}</div>
        {!visibleDevices.length && <EmptyState title="该分类暂无设备" description="选择其他分类或等待设备接入。" />}
        {light && <div className="range-row"><div className="range-label"><span>目标亮度</span><strong>{draft ?? confirmed}%</strong></div><input aria-label="目标灯光亮度" type="range" min="0" max="100" value={draft ?? confirmed} disabled={disabled(light)} onChange={e => setDraft(Number(e.target.value))} /><p className="form-help">设备已确认：{typeof light.state.brightness === 'number' ? `${confirmed}%` : '未知'}。调整后点击应用。</p><button className="button" disabled={disabled(light) || draft === null} onClick={() => void execute(light, { brightness: draft ?? confirmed })}>{pendingCommands[light.device_id] ? '正在设置…' : '应用亮度'}</button></div>}
      </Panel>
    </div>
    <div className="integration-grid">
      <Panel title="自动温控" description="温度过高时，由硬件或后端自动启动风扇。"><StatusBadge tone="warning">联动信息待接入</StatusBadge><p className="integration-copy">温度阈值：— 控制模式：—<br />启动原因：等待后端提供，当前不推断自动联动结果。</p></Panel>
      <Panel title="门禁核验" description="授权身份与实际开门结果分别展示。"><StatusBadge tone="warning">门禁回执待接入</StatusBadge><p className="integration-copy">前往“监控与识别”查看人脸核验。识别通过不等于门已打开。</p></Panel>
    </div>
    <Panel title="最近活动" description="记录设备状态变化与控制操作。">{snapshot?.recent_events.length ? <div className="event-list">{snapshot.recent_events.map(e => <div className="event-item" key={e.event_id}><span className="event-marker" /><div><strong>{e.device_name}</strong><p>{deviceStateText(e.state)}</p></div><span className="event-time">{formatDateTime(e.occurred_at)}</span></div>)}</div> : <EmptyState title="暂无活动" description="设备状态变化后会显示在这里。" />}</Panel>
  </>;
}
function Card({ title, value, note, icon }: { title: string; value: string; note: string; icon: React.ReactNode }) {
  return <article className="kpi-card"><div className="kpi-top"><span>{title}</span>{icon}</div><div className="kpi-value">{value}</div><div className="kpi-meta">{note}</div></article>;
}
