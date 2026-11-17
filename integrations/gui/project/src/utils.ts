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

export function deviceStateText(state: Record<string, boolean | number | string>, kind?: import('./types/contracts').DeviceKind) {
  return Object.entries(state).filter(([key]) => key !== 'pin').map(([key, value]) => {
    if (key === 'position') return value === 'open' ? '开启' : value === 'closed' ? '关闭' : value === 'moving' ? '移动中' : '未知';
    if (key === 'locked') return value ? '已上锁' : '已解锁';
    if (key === 'power') return kind === 'voice' ? value ? '已启用' : '已禁用' : value ? '运行中' : '已关闭';
    if (key === 'brightness') return `亮度 ${value}%`;
    if (key === 'color') return `颜色 ${value}`;
    if (key === 'led_count') return `灯珠 ${value}`;
    if (key === 'speed') return `风速 ${value}`;
    if (key === 'mode') return value === 'auto' ? '自动模式' : value === 'manual' ? '手动模式' : '模式未知';
    if (key === 'state_basis') return value === 'actuator' ? '执行器反馈，未验证物理位置' : `状态依据：${value}`;
    if (key === 'target_temperature') return `设定 ${value}°C`;
    return `${key}: ${String(value)}`;
  }).join(' · ');
}

export function deviceEventActionText(event: import('./types/contracts').DeviceEvent) {
  const labels: Record<string, string> = {
    set: '状态更新', keypad_granted: '键盘密码通过', keypad_denied: '键盘密码拒绝',
    rfid_granted: '刷卡通过', rfid_denied: '刷卡拒绝', voice: '本地语音',
  };
  const parts = [labels[event.action] ?? event.action];
  const commands = ['开风扇', '关风扇', '开灯', '关灯', '开入户门', '关入户门'];
  const command = event.command;
  if (event.action === 'voice' && typeof command === 'number' && Number.isInteger(command) && command >= 1 && command <= 6) parts.push(commands[command - 1]);
  return parts.join(' · ');
}

export function toIsoRange(startLocal: string, endLocal: string) {
  return { start: new Date(startLocal).toISOString(), end: new Date(endLocal).toISOString() };
}

export function localDateTimeValue(date: Date, includeSeconds = false) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, includeSeconds ? 19 : 16);
}

export function deviceAction(device: import('./types/contracts').DeviceState) {
  if (device.kind === 'door') return device.state.position === 'open' ? '关门' : '开门';
  if (device.kind === 'window') return device.state.position === 'open' ? '关窗' : '开窗';
  if (device.kind === 'lock') return device.state.locked ? '解锁' : '上锁';
  if (device.kind === 'light') return device.state.power ? '关灯' : '开灯';
  if (device.kind === 'voice') return device.state.power ? '禁用语音' : '启用语音';
  return device.state.power ? '关闭' : '启动';
}
export function positionText(device?: import('./types/contracts').DeviceState) {
  if (!device) return '未接入';
  if (device.status !== 'online') return device.status === 'offline' ? '离线' : '未知';
  const position = device.state.position === 'open' ? '开启' : device.state.position === 'closed' ? '关闭' : device.state.position === 'moving' ? '移动中' : '未知';
  return device.state.state_basis === 'actuator' ? `执行器：${position}` : position;
}
