import type { DashboardSnapshot, DataMode, SystemStatus } from '@/types/contracts';

export function isHardwareSimulation(mode: DataMode, status: SystemStatus | null, snapshot: DashboardSnapshot | null): boolean {
  return mode === 'mock' || status?.hardware_mode === 'mock' || snapshot?.freshness === 'mock';
}
