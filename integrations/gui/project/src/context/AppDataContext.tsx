import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { dataMode, dataSource } from '@/services';
import type { DashboardSnapshot, DeviceCommand, DeviceCommandInput, SmartHomeDataSource, SystemStatus } from '@/types/contracts';
import { errorMessage } from '@/utils';

interface AppDataValue {
  source: SmartHomeDataSource;
  mode: typeof dataMode;
  status: SystemStatus | null;
  snapshot: DashboardSnapshot | null;
  loading: boolean;
  error: string;
  connectionError: string;
  lastSuccess: number;
  pendingCommands: Record<string, boolean>;
  refresh: () => Promise<void>;
  sendCommand: (input: DeviceCommandInput) => Promise<DeviceCommand>;
}

const AppDataContext = createContext<AppDataValue | null>(null);

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [lastSuccess, setLastSuccess] = useState(0);
  const activeCommands = useRef(new Set<string>());
  const refreshSequence = useRef(0);
  const [pendingCommands, setPendingCommands] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    try {
      const [nextStatus, nextSnapshot] = await Promise.all([
        dataSource.getSystemStatus(),
        dataSource.getDashboardSnapshot(),
      ]);
      if (sequence !== refreshSequence.current) return;
      setConnectionError('');
      setLastSuccess(Date.now());
      setStatus(nextStatus);
      setSnapshot(nextSnapshot);
    } catch (reason) {
      if (sequence === refreshSequence.current) setConnectionError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const unsubscribe = dataSource.subscribeEvents((event) => {
      if (event.type !== 'recognition.created' && event.type !== 'command.updated') void refresh();
    });
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => { unsubscribe(); window.clearInterval(timer); };
  }, [refresh]);

  const sendCommand = useCallback(async (input: DeviceCommandInput) => {
    if (dataMode === 'http' && !navigator.onLine) throw new Error('网络已断开，暂时无法发送控制命令。');
    if (activeCommands.current.has(input.device_id)) throw new Error('该设备正在执行指令，请稍候。');
    activeCommands.current.add(input.device_id);
    setPendingCommands((current) => ({ ...current, [input.device_id]: true }));
    setError('');
    try {
      let command = await dataSource.sendDeviceCommand(input);
      const deadline = Date.now() + 30000;
      while (command.status === 'pending' && Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        command = await dataSource.getDeviceCommand(command.command_id);
      }
      if (command.status === 'pending' || command.status === 'timeout') throw new Error('设备确认超时，执行结果未知。请刷新核对状态，不要重复发送。');
      if (command.status !== 'acked') throw new Error(command.error_message || '设备执行失败。');
      await refresh();
      return command;
    } catch (reason) {
      setError(errorMessage(reason));
      throw reason;
    } finally {
      activeCommands.current.delete(input.device_id);
      setPendingCommands((current) => ({ ...current, [input.device_id]: false }));
    }
  }, [refresh]);

  const value = useMemo<AppDataValue>(() => ({
    source: dataSource, mode: dataMode, status, snapshot, loading, error, connectionError, lastSuccess,
    pendingCommands, refresh, sendCommand,
  }), [status, snapshot, loading, error, connectionError, lastSuccess, pendingCommands, refresh, sendCommand]);

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData() {
  const value = useContext(AppDataContext);
  if (!value) throw new Error('useAppData 必须在 AppDataProvider 内使用。');
  return value;
}
