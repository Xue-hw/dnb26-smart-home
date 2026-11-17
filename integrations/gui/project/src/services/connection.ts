import { Capacitor, registerPlugin } from '@capacitor/core';
import type { DataMode } from '@/types/contracts';

const BASE_KEY = 'dnb26_backend_url';
const MODE_KEY = 'dnb26_data_mode';
const TOKEN_KEY = 'dnb26_admin_token';
const TOKEN_BASE_KEY = 'dnb26_admin_token_backend';
const REMEMBER_KEY = 'dnb26_admin_remember_backend';

interface AdminVault {
  get(options: { backend: string }): Promise<{ token: string }>;
  set(options: { backend: string; token: string }): Promise<void>;
  clear(): Promise<void>;
}
const vault = registerPlugin<AdminVault>('AdminVault');
function effectiveBase(base: string): string { return base || window.location.origin; }
export function rememberAdmin(): string { return window.localStorage.getItem(REMEMBER_KEY) || ''; }

function storeSessionToken(token: string, base: string): void {
  if (token) {
    window.sessionStorage.setItem(TOKEN_KEY, token);
    window.sessionStorage.setItem(TOKEN_BASE_KEY, base);
  } else {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.sessionStorage.removeItem(TOKEN_BASE_KEY);
  }
}

export async function restoreAdminSession(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  const temporaryToken = adminToken();
  storeSessionToken('', '');
  const base = effectiveBase(backendBase());
  // Native preferences commit synchronously; WebView localStorage may not flush
  // before a force-stop. The encrypted backend-bound record is authoritative.
  const saved = await vault.get({ backend: base });
  if (saved.token) window.localStorage.setItem(REMEMBER_KEY, base);
  else window.localStorage.removeItem(REMEMBER_KEY);
  storeSessionToken(saved.token || temporaryToken, base);
}

async function browserSession(base: string, method: 'POST' | 'DELETE', token = ''): Promise<void> {
  if (base !== window.location.origin) throw new Error('网页持久管理员权限仅支持同源后端，请直接打开该后端网页。');
  const response = await fetch(`${base}/api/auth/session`, {
    method, credentials: 'same-origin', headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(method === 'POST' ? '管理员令牌无效或持久授权保存失败。' : '退出管理员权限失败，请检查连接后重试。');
}

export function validateBackendUrl(value: string): string {
  const text = value.trim();
  if (!text) return '';
  const parsed = new URL(text);
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/') {
    throw new Error('后端地址应为 HTTP/HTTPS 源地址，例如 http://192.168.137.2:8080，不含路径、账户或参数。');
  }
  return parsed.origin;
}
export function backendBase(): string {
  const saved = window.localStorage.getItem(BASE_KEY);
  const fallback = Capacitor.isNativePlatform() ? 'http://192.168.137.2:8080' : '';
  return validateBackendUrl(saved || import.meta.env.VITE_API_BASE_URL || fallback);
}
export function configuredMode(): DataMode {
  const mode = window.localStorage.getItem(MODE_KEY) || import.meta.env.VITE_DATA_MODE;
  return mode === 'mock' ? 'mock' : 'http';
}
export function adminToken(): string {
  const savedBase = window.sessionStorage.getItem(TOKEN_BASE_KEY);
  if (!savedBase || savedBase !== effectiveBase(backendBase())) return '';
  return window.sessionStorage.getItem(TOKEN_KEY) || '';
}
export function backendUrl(path: string): string {
  if (!path) return '';
  if (/^https?:\/\//i.test(path) || path.startsWith('blob:') || path.startsWith('data:')) return path;
  return `${backendBase()}${path.startsWith('/') ? path : `/${path}`}`;
}
export async function saveConnection(base: string, mode: DataMode, token: string, remember = false): Promise<void> {
  const validated = validateBackendUrl(base);
  const target = effectiveBase(validated);
  const secret = token.trim();
  if (remember && mode === 'mock') throw new Error('请在真实后端模式下保存管理员权限。');
  if (remember) {
    if (Capacitor.isNativePlatform()) {
      if (!secret) throw new Error('请输入管理员令牌。');
      const response = await fetch(`${target}/api/auth/status`, { headers: { Authorization: `Bearer ${secret}` }, signal: AbortSignal.timeout(15000) });
      if (!response.ok || !(await response.json()).write_access) throw new Error('管理员令牌无效，未保存持久权限。');
      await vault.set({ backend: target, token: secret });
    } else if (secret) {
      await browserSession(target, 'POST', secret);
    } else {
      if (target !== window.location.origin || rememberAdmin() !== target) throw new Error('首次持久授权需要填写管理员令牌。');
      const response = await fetch(`${target}/api/auth/status`, { credentials: 'same-origin', signal: AbortSignal.timeout(15000) });
      const access = await response.json();
      if (!response.ok || !access.write_access || !access.persistent_admin) throw new Error('持久授权已失效，请重新填写管理员令牌。');
    }
  } else if (rememberAdmin()) {
    await clearAdminAccess();
  }
  window.localStorage.setItem(BASE_KEY, validated);
  window.localStorage.setItem(MODE_KEY, mode);
  if (remember) window.localStorage.setItem(REMEMBER_KEY, target);
  else window.localStorage.removeItem(REMEMBER_KEY);
  storeSessionToken(remember && !Capacitor.isNativePlatform() ? '' : secret, target);
}

export async function clearAdminAccess(): Promise<void> {
  if (Capacitor.isNativePlatform()) await vault.clear();
  else await browserSession(rememberAdmin() || window.location.origin, 'DELETE');
  window.localStorage.removeItem(REMEMBER_KEY);
  storeSessionToken('', '');
}
