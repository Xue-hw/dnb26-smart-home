import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, Save, Server } from 'lucide-react';
import { useAppData } from '@/context/AppDataContext';
import { adminToken, backendBase, clearAdminAccess, rememberAdmin, saveConnection } from '@/services/connection';
import type { DataMode, ModelStatus, RuntimeSettings } from '@/types/contracts';
import { errorMessage } from '@/utils';
import { ErrorState, PageHeader, Panel, StatusBadge } from '@/components/Common';
import { SystemAlerts } from '@/components/SystemAlerts';
import { HardwareBoards } from '@/components/HardwareBoards';
import { isHardwareSimulation } from '@/services/hardwarePolicy';

export default function SystemPage() {
  const { source, status, snapshot, mode, connectionError, refresh: refreshStatus } = useAppData();
  const simulatedHardware = isHardwareSimulation(mode, status, snapshot);
  const [base, setBase] = useState(backendBase());
  const [nextMode, setNextMode] = useState<DataMode>(mode);
  const [token, setToken] = useState(adminToken());
  const [remember, setRemember] = useState(Boolean(rememberAdmin()));
  const [connecting, setConnecting] = useState(false);
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [savedSettings, setSavedSettings] = useState<RuntimeSettings | null>(null);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [access, setAccess] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const settingsGeneration = useRef(0);
  const savingSettings = useRef(false);
  const refresh = useCallback(async () => {
    if (savingSettings.current) return;
    const generation = ++settingsGeneration.current;
    await refreshStatus();
    if (generation !== settingsGeneration.current || savingSettings.current) return;
    const results = await Promise.allSettled([source.getSettings(), source.getModels(), source.getAuthStatus()]);
    if (generation !== settingsGeneration.current || savingSettings.current) return;
    const problems: string[] = [];
    if (results[0].status === 'fulfilled') { setSettings(results[0].value); setSavedSettings(results[0].value); } else { setSavedSettings(null); problems.push(errorMessage(results[0].reason)); }
    if (results[1].status === 'fulfilled') setModels(results[1].value.items || []); else problems.push(errorMessage(results[1].reason));
    if (results[2].status === 'fulfilled') setAccess(results[2].value.write_access); else { setAccess(false); problems.push(errorMessage(results[2].reason)); }
    setError(problems.join('；'));
  }, [source, refreshStatus]);
  const invalidateSettings = useCallback(() => { settingsGeneration.current += 1; }, []);
  useEffect(() => { void refresh(); return invalidateSettings; }, [refresh, invalidateSettings]);
  async function connect() {
    if (connecting) return;
    setConnecting(true); setError('');
    try { await saveConnection(base, nextMode, token, remember); window.location.reload(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setConnecting(false); }
  }
  async function logout() {
    if (connecting) return;
    setConnecting(true); setError('');
    try { await clearAdminAccess(); window.location.reload(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setConnecting(false); }
  }
  async function saveSettings() {
    if (!settings || !access || savingSettings.current) return;
    if (!(settings.temperature_on > settings.temperature_off)) { setError('开启温度必须高于关闭温度，避免风扇频繁切换。'); return; }
    savingSettings.current = true;
    const generation = ++settingsGeneration.current;
    setSaving(true); setMessage('');
    try {
      const saved = await source.updateSettings(settings);
      if (generation !== settingsGeneration.current) return;
      setSettings(saved); setSavedSettings(saved); setError(''); setMessage('配置已保存在后端，等待硬件确认；保存成功不代表 UNO1 已应用。');
    }
    catch (reason) { if (generation === settingsGeneration.current) setError(errorMessage(reason)); }
    finally { savingSettings.current = false; if (generation === settingsGeneration.current) setSaving(false); }
  }
  const uno1 = status?.hardware_boards?.uno1;
  const temperatureSynced = !simulatedHardware && !connectionError && uno1?.status === 'online' && uno1.temperature_config_synced === true && savedSettings !== null && typeof uno1.temperature_on === 'number' && typeof uno1.temperature_off === 'number' && Math.abs(uno1.temperature_on - savedSettings.temperature_on) < 0.000001 && Math.abs(uno1.temperature_off - savedSettings.temperature_off) < 0.000001;
  return <>
    <PageHeader eyebrow="06 / SYSTEM" title="系统状态与连接设置" description="查看服务、模型与报警；设置网页或 APK 使用的后端地址。" actions={<button className="button secondary" disabled={saving} onClick={() => void refresh()}><RefreshCw size={15} />检查服务</button>} />
    {error && <ErrorState message={error} />}{message && <div className="result-summary" role="status">{message}</div>}
    <div className="integration-grid"><Panel title="后端连接" description="网页同源部署时地址留空。手机上的 localhost 指手机本身。">
      <div className="form-field"><label htmlFor="backend-address">后端地址</label><input id="backend-address" value={base} placeholder="http://192.168.137.2:8080" onChange={event => { setBase(event.target.value); setToken(''); }} /></div>
      <div className="form-field"><label htmlFor="data-mode">数据模式</label><select id="data-mode" value={nextMode} onChange={event => setNextMode(event.target.value as DataMode)}><option value="http">真实后端 HTTP</option><option value="mock">独立演示 Mock</option></select></div>
      <div className="form-field"><label htmlFor="admin-token">管理员令牌（可选）</label><input id="admin-token" type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></div>
      <label className="check-setting"><input id="remember-admin" type="checkbox" checked={remember} disabled={connecting} onChange={event => setRemember(event.target.checked)} />记住本设备的管理员权限</label>
      <p className="form-help">勾选后重开可恢复权限：网页使用一年有效的 HttpOnly 会话，APK 使用设备密钥加密保存。仅在本人管理的设备使用；退出可清除本设备授权。网页持久权限限同源后端；切换后端需重新授权。跨网络连接建议使用 HTTPS/VPN。</p>
      <button className="button" disabled={connecting} onClick={() => void connect()}><Server size={15} />{connecting ? '正在处理…' : '保存连接并重新加载'}</button>{(access || token || rememberAdmin()) && <button className="button secondary" disabled={connecting} onClick={() => void logout()}>退出管理员权限</button>}
    </Panel><Panel title="服务状态" description="在线状态来自后端检查，摄像头和硬件分别展示。"><div className="service-list">{(['backend', 'database', 'camera', 'hardware'] as const).map(key => <div key={key}><strong>{{ backend: '后端', database: 'MySQL', camera: '摄像头', hardware: 'Arduino' }[key]}</strong><StatusBadge tone={key === 'hardware' && simulatedHardware ? 'warning' : status?.[key] === 'online' ? 'success' : 'warning'}>{key === 'hardware' && simulatedHardware ? '未接入 · 模拟回执' : status?.[key] === 'online' ? '在线' : status?.[key] === 'offline' ? '离线' : '未知'}</StatusBadge></div>)}</div><HardwareBoards boards={status?.hardware_boards} simulated={simulatedHardware} /><p>{status?.message}</p><p className="form-help">硬件模式：{status?.hardware_mode || '以服务端状态为准'} · 写入权限：{access ? '已授权' : '只读或未授权'}</p></Panel></div>
    <SystemAlerts />
    <div className="integration-grid"><Panel title="模型状态" description="列出自定义、通用 YOLO 和人脸模型的实际加载情况。">{models.length ? models.map(model => <article key={model.name} className="live-face"><strong>{model.name}</strong> <StatusBadge tone={['online', 'ready', 'loaded'].includes(model.status) ? 'success' : 'warning'}>{model.status}</StatusBadge><p>{model.classes?.join('、') || '无类别信息'}</p><small>{model.message}</small></article>) : <p>尚未获取模型状态</p>}</Panel>
    <Panel title="联动与保留策略" description="自动控制由后端或 Arduino 执行，浏览器不自行控制硬件。">{settings ? <><div className="settings-fields">{([{ key: 'temperature_on', label: '风扇开启温度 °C', min: -20, max: 80 }, { key: 'temperature_off', label: '风扇关闭温度 °C', min: -20, max: 80 }, { key: 'door_open_seconds', label: '门未关提醒秒数', min: 5, max: 3600 }, { key: 'retention_days', label: '照片保留天数', min: 1, max: 365 }] as const).map(field => <div className="form-field" key={field.key}><label htmlFor={field.key}>{field.label}</label><input id={field.key} type="number" min={field.min} max={field.max} step={status?.hardware_mode === 'gateway' && field.key.startsWith('temperature_') ? 0.1 : 1} value={settings[field.key]} onChange={event => setSettings({ ...settings, [field.key]: Number(event.target.value) })} /></div>)}</div><>{status?.hardware_mode === 'gateway' && <div className="result-summary" aria-label="UNO1 温控同步状态"><StatusBadge tone={temperatureSynced ? 'success' : 'warning'}>{temperatureSynced ? '温控阈值已同步' : '温控阈值待同步'}</StatusBadge><p>后端已保存：开启 {savedSettings?.temperature_on ?? '—'}°C / 关闭 {savedSettings?.temperature_off ?? '—'}°C</p><p>UNO1 报告：开启 {uno1?.temperature_on ?? '—'}°C / 关闭 {uno1?.temperature_off ?? '—'}°C</p><p className="form-help">编辑框是待保存值；仅在线 UNO1 回报的阈值与后端已保存值一致且确认同步后显示已同步。</p></div>}</><label className="check-setting"><input type="checkbox" checked={settings.bulb_linkage} onChange={event => setSettings({ ...settings, bulb_linkage: event.target.checked })} />允许灯泡识别联动（须模型和硬件均可用）</label><button className="button" disabled={!access || saving} onClick={() => void saveSettings()}><Save size={15} />{saving ? '正在保存…' : '保存后端配置'}</button></> : <p>配置尚未加载成功。</p>}</Panel></div>
  </>;
}
