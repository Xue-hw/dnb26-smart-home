import type { SystemStatus } from '@/types/contracts';
import { StatusBadge } from './Common';

export function HardwareBoards({ boards, simulated = false }: { boards?: SystemStatus['hardware_boards']; simulated?: boolean }) {
  if (!boards || !Object.keys(boards).length) return null;
  return <div className="service-list" aria-label="Arduino 分板连接状态">{Object.entries(boards).map(([id, board]) => <div key={id}>
    <div><strong>{id.toUpperCase()}</strong><p className="form-help">{board.message || '未返回板卡说明'}</p><small>{board.capabilities?.join('、') || '未报告硬件能力'}</small></div>
    <StatusBadge tone={!simulated && board.status === 'online' ? 'success' : 'warning'}>{simulated ? '模拟 · 未接实机' : board.status === 'online' ? '在线' : board.status === 'offline' ? '离线' : '未知'}</StatusBadge>
  </div>)}</div>;
}
