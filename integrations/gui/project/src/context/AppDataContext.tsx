import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { dataMode, dataSource } from '@/services';
import { createRefreshQueue } from '@/services/refreshQueue';
import type { DashboardSnapshot, DeviceCommand, DeviceCommandInput, ServerClock, SmartHomeDataSource, SystemStatus } from '@/types/contracts';
import { errorMessage } from '@/utils';

interface AppDataValue {
  source: SmartHomeDataSource;
  mode: typeof dataMode;
  status: SystemStatus | null;
  snapshot: DashboardSnapshot | null;
  serverClock: ServerClock | null;
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
  const [serverClock, setServerClock] = useState<ServerClock | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [lastSuccess, setLastSuccess] = useState(0);
  const activeCommands = useRef(new Set<string>());
  const refreshQueue = useRef<ReturnType<typeof createRefreshQueue> | null>(null);
  const [pendingCommands, setPendingCommands] = useState<Record<string, boolean>>({});

  const refresh = useCallback(() => refreshQueue.current?.request() ?? Promise.resolve(), []);

  useEffect(() => {
    let active = true;
    const queue = createRefreshQueue(async () => {
      try {
        // Wait for both reads even on failure, so the next batch cannot overlap
        // the unfinished half of this pair. The HTTP adapter bounds each read.
        const [nextStatus, nextSnapshot] = await Promise.allSettled([
          dataSource.getSystemStatus(),
          dataSource.getDashboardSnapshot(),
        ]);
        if (!active) return;
        if (nextStatus.status === 'rejected') throw nextStatus.reason;
        if (nextSnapshot.status === 'rejected') throw nextSnapshot.reason;
        setConnectionError('');
        setLastSuccess(Date.now());
        const serverTimestamp = Date.parse(nextStatus.value.server_time);
        if (Number.isFinite(serverTimestamp)) setServerClock({ timestamp: serverTimestamp, receivedAt: performance.now(), browserOffset: serverTimestamp - Date.now() });
        setStatus(nextStatus.value);
        setSnapshot(nextSnapshot.value);
      } catch (reason) {
        if (active) setConnectionError(errorMessage(reason));
      } finally {
        if (active) setLoading(false);
      }
    });
    refreshQueue.current = queue;
    void refresh();
    const unsubscribe = dataSource.subscribeEvents((event) => {
      if (event.type !== 'recognition.created' && event.type !== 'command.updated') void refresh();
    });
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => {
      active = false;
      unsubscribe();
      window.clearInterval(timer);
      queue.dispose();
      if (refreshQueue.current === queue) refreshQueue.current = null;
    };
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
      if ('pin' in input.params) {
        const safeMessage = '修改设备 PIN 失败，请检查权限、连接和控制器回执。';
        setError(safeMessage);
        throw new Error(safeMessage);
      }
      setError(errorMessage(reason));
      throw reason;
    } finally {
      activeCommands.current.delete(input.device_id);
      setPendingCommands((current) => ({ ...current, [input.device_id]: false }));
    }
  }, [refresh]);

  const value = useMemo<AppDataValue>(() => ({
    source: dataSource, mode: dataMode, status, snapshot, serverClock, loading, error, connectionError, lastSuccess,
    pendingCommands, refresh, sendCommand,
  }), [status, snapshot, serverClock, loading, error, connectionError, lastSuccess, pendingCommands, refresh, sendCommand]);

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData() {
  const value = useContext(AppDataContext);
  if (!value) throw new Error('useAppData 必须在 AppDataProvider 内使用。');
  return value;
}
