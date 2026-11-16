import { useState } from 'react';
import type { DeviceState } from '@/types/contracts';

type Params = Record<string, boolean | number | string>;

export function DeviceExtras({ device, disabled, execute }: { device: DeviceState; disabled: boolean; execute: (params: Params) => Promise<boolean> }) {
  const [color, setColor] = useState<string | null>(null);
  const [count, setCount] = useState<string | null>(null);
  const [speed, setSpeed] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const supports = (capability: string) => device.capabilities?.includes(capability);
  const hasColor = device.kind === 'light' && supports('color');
  const hasCount = device.kind === 'light' && supports('led_count');
  const hasSpeed = device.kind === 'fan' && supports('speed');
  const hasPin = device.kind === 'door' && supports('pin');
  if (!hasColor && !hasCount && !hasSpeed && !hasPin) return null;
  const validInteger = (value: string | null, min: number, max: number) => value !== null && /^\d+$/.test(value) && Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max;
  const actualColor = typeof device.state.color === 'string' && /^#[0-9a-f]{6}$/i.test(device.state.color) ? device.state.color : null;
  return <div className="device-extra-controls" aria-label={`${device.name}扩展控制`}>
    {hasColor && <div className="form-field"><label htmlFor={`${device.device_id}-color`}>灯带颜色</label><input id={`${device.device_id}-color`} type="color" value={color ?? actualColor ?? '#ffffff'} disabled={disabled} onChange={event => setColor(event.target.value)} /><small>当前反馈：{actualColor ?? '未报告'}</small><button className="button secondary small" disabled={disabled || color === null || !/^#[0-9a-f]{6}$/i.test(color)} onClick={() => { if (color) void execute({ color }).then(ok => { if (ok) setColor(null); }); }}>应用颜色</button></div>}
    {hasCount && <div className="form-field"><label htmlFor={`${device.device_id}-led-count`}>点亮灯珠数（1–8）</label><input id={`${device.device_id}-led-count`} type="number" min="1" max="8" step="1" value={count ?? (typeof device.state.led_count === 'number' ? String(device.state.led_count) : '')} disabled={disabled} onChange={event => setCount(event.target.value)} /><small>当前反馈：{typeof device.state.led_count === 'number' ? device.state.led_count : '未报告'}</small><button className="button secondary small" disabled={disabled || !validInteger(count, 1, 8)} onClick={() => void execute({ led_count: Number(count) }).then(ok => { if (ok) setCount(null); })}>应用灯珠数</button></div>}
    {hasSpeed && <div className="form-field"><label htmlFor={`${device.device_id}-speed`}>风扇速度（0–100）</label><input id={`${device.device_id}-speed`} type="number" min="0" max="100" step="1" value={speed ?? (typeof device.state.speed === 'number' ? String(device.state.speed) : '')} disabled={disabled} onChange={event => setSpeed(event.target.value)} /><small>当前反馈：{typeof device.state.speed === 'number' ? device.state.speed : '未报告'}</small><button className="button secondary small" disabled={disabled || !validInteger(speed, 0, 100)} onClick={() => void execute({ speed: Number(speed) }).then(ok => { if (ok) setSpeed(null); })}>应用风速</button></div>}
    {hasPin && <form className="form-field" onSubmit={event => { event.preventDefault(); if (!disabled && /^\d{4}$/.test(pin)) void execute({ pin }).then(ok => { if (ok) setPin(''); }); }}><label htmlFor={`${device.device_id}-pin`}>新 PIN（4 位数字）</label><input id={`${device.device_id}-pin`} type="password" inputMode="numeric" autoComplete="new-password" pattern="[0-9]{4}" maxLength={4} value={pin} disabled={disabled} onChange={event => setPin(event.target.value)} /><small>不读取原密码；控制器确认成功后清空输入。</small><button className="button secondary small" disabled={disabled || !/^\d{4}$/.test(pin)} type="submit">修改 PIN</button></form>}
  </div>;
}
