export function formatDateTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date).replaceAll('/', '-');
}

export function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '发生未知错误，请重试。';
}

export function deviceStateText(state: Record<string, boolean | number | string>) {
  return Object.entries(state).map(([key, value]) => {
    if (key === 'position') return value === 'open' ? '开启' : value === 'closed' ? '关闭' : '未知';
    if (key === 'locked') return value ? '已上锁' : '已解锁';
    if (key === 'power') return value ? '运行中' : '已关闭';
    if (key === 'brightness') return `亮度 ${value}%`;
    if (key === 'target_temperature') return `设定 ${value}°C`;
    return `${key}: ${String(value)}`;
  }).join(' · ');
}

export function toIsoRange(startLocal: string, endLocal: string) {
  return { start: new Date(startLocal).toISOString(), end: new Date(endLocal).toISOString() };
}

export function localDateTimeValue(date: Date) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function deviceAction(device: import('./types/contracts').DeviceState) {
  if (device.kind === 'door') return device.state.position === 'open' ? '关门' : '开门';
  if (device.kind === 'window') return device.state.position === 'open' ? '关窗' : '开窗';
  if (device.kind === 'lock') return device.state.locked ? '解锁' : '上锁';
  if (device.kind === 'light') return device.state.power ? '关灯' : '开灯';
  return device.state.power ? '关闭' : '启动';
}
export function positionText(device?: import('./types/contracts').DeviceState) {
  if (!device) return '未接入';
  if (device.status !== 'online') return device.status === 'offline' ? '离线' : '未知';
  return device.state.position === 'open' ? '开启' : device.state.position === 'closed' ? '关闭' : '未知';
}
