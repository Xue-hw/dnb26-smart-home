import { useCallback, useEffect, useState } from 'react';
import { Bell, RefreshCw } from 'lucide-react';
import { useAppData } from '@/context/AppDataContext';
import type { SystemAlert } from '@/types/contracts';
import { errorMessage, formatDateTime } from '@/utils';
import { EmptyState, ErrorState, Panel, StatusBadge } from './Common';

export function SystemAlerts({ compact = false }: { compact?: boolean }) {
  const { source, mode } = useAppData();
  const [items, setItems] = useState<SystemAlert[]>([]);
  const [error, setError] = useState('');
  const [pending, setPending] = useState('');
  const refresh = useCallback(async () => {
    try { const result = await source.getAlerts(); setItems(result.items || []); setError(''); }
    catch (reason) { setError(errorMessage(reason)); }
  }, [source]);
  useEffect(() => { let active = true; const load = () => { if (active) void refresh(); }; load(); const timer = window.setInterval(load, 10000); return () => { active = false; clearInterval(timer); }; }, [refresh]);
  async function acknowledge(id: string) {
    setPending(id);
    try { await source.acknowledgeAlert(id); await refresh(); }
    catch (reason) { setError(errorMessage(reason)); }
    finally { setPending(''); }
  }
  return <Panel className={compact ? 'alerts-compact' : ''} title="系统报警" description="确认表示已阅读，不代表故障已恢复。设备未接入时不推断其正常。" icon={<Bell size={18} />} actions={<button className="button secondary small" onClick={() => void refresh()}><RefreshCw size={14} />刷新报警</button>}>
    {error && <ErrorState message={error} />}
    {mode === 'mock' && <p className="form-help">当前为模拟模式，不读取真实故障。</p>}
    {items.length ? <div className="event-list">{items.map(item => <article className="event-item alert-item" key={item.id}><div><StatusBadge tone={!item.active ? 'success' : ['critical', 'error'].includes(item.severity) ? 'danger' : 'warning'}>{!item.active ? '已恢复' : item.acknowledged ? '故障持续 · 已确认' : '故障持续'}</StatusBadge><p>{item.message}</p><small>{item.code} · {formatDateTime(item.created_at)}{item.resolved_at && ` · 恢复 ${formatDateTime(item.resolved_at)}`}</small></div>{item.active && !item.acknowledged && <button className="button secondary small" disabled={Boolean(pending)} onClick={() => void acknowledge(item.id)}>{pending === item.id ? '正在确认…' : '确认已阅读'}</button>}</article>)}</div> : !error && <EmptyState title="暂无报警记录" description="此处显示后端报告的系统故障和恢复事件。" />}
  </Panel>;
}
