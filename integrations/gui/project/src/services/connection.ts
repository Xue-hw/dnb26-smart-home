import { Capacitor } from '@capacitor/core';
import type { DataMode } from '@/types/contracts';

const BASE_KEY = 'dnb26_backend_url';
const MODE_KEY = 'dnb26_data_mode';
const TOKEN_KEY = 'dnb26_admin_token';

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
export function adminToken(): string { return window.sessionStorage.getItem(TOKEN_KEY) || ''; }
export function backendUrl(path: string): string {
  if (!path) return '';
  if (/^https?:\/\//i.test(path) || path.startsWith('blob:') || path.startsWith('data:')) return path;
  return `${backendBase()}${path.startsWith('/') ? path : `/${path}`}`;
}
export function saveConnection(base: string, mode: DataMode, token: string): void {
  const validated = validateBackendUrl(base);
  window.localStorage.setItem(BASE_KEY, validated);
  window.localStorage.setItem(MODE_KEY, mode);
  if (token.trim()) window.sessionStorage.setItem(TOKEN_KEY, token.trim());
  else window.sessionStorage.removeItem(TOKEN_KEY);
}
