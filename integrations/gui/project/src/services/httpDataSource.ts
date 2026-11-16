import { adminToken, backendUrl } from './connection';
import {
  ApiError,
  type DetectionRequest,
  type DeviceCommandInput,
  type HistoryQuery,
  type PersonInput,
  type RealtimeEvent,
  type RealtimeEventType,
  type SmartHomeDataSource,
} from '@/types/contracts';

const REALTIME_EVENTS: RealtimeEventType[] = [
  'sensor.updated',
  'device.state.changed',
  'command.updated',
  'recognition.created',
  'camera.status.changed',
  'system.status.changed',
];

function queryString(query: object) {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== '') params.set(key, String(value));
  });
  const text = params.toString();
  return text ? `?${text}` : '';
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(backendUrl(path), {
      ...init,
      signal: controller.signal,
      headers: { ...(init.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...(adminToken() ? { Authorization: `Bearer ${adminToken()}` } : {}), ...init.headers },
    });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const rawDetail = typeof payload === 'object' && payload ? payload.detail || payload.message || payload.msg : payload;
      const detail = Array.isArray(rawDetail) ? rawDetail.map(item => typeof item === 'object' && item ? item.msg : String(item)).join('；') : rawDetail;
      throw new ApiError(typeof detail === 'string' ? detail : `HTTP ${response.status}`, response.status, 'HTTP_ERROR', payload);
    }
    return normalizeMedia(payload) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请检查后端或网络状态。', 408, 'REQUEST_TIMEOUT');
    }
    throw new ApiError(error instanceof Error ? error.message : '网络请求失败。', 0, 'NETWORK_ERROR');
  } finally {
    window.clearTimeout(timeout);
  }
}

function normalizeMedia(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeMedia);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
    ['image_url', 'avatar_url', 'archive_url'].includes(key) && typeof item === 'string' ? backendUrl(item) : normalizeMedia(item),
  ]));
}

export class HttpDataSource implements SmartHomeDataSource {
  getSystemStatus() {
    return request<ReturnType<SmartHomeDataSource['getSystemStatus']> extends Promise<infer T> ? T : never>('/api/system/status');
  }

  getDashboardSnapshot() {
    return request<ReturnType<SmartHomeDataSource['getDashboardSnapshot']> extends Promise<infer T> ? T : never>('/api/dashboard/snapshot');
  }

  getSensorHistory(query: HistoryQuery) {
    return request<ReturnType<SmartHomeDataSource['getSensorHistory']> extends Promise<infer T> ? T : never>(`/api/sensors/history${queryString(query)}`);
  }

  getDeviceEvents(query: HistoryQuery) {
    return request<ReturnType<SmartHomeDataSource['getDeviceEvents']> extends Promise<infer T> ? T : never>(`/api/devices/events${queryString(query)}`);
  }

  sendDeviceCommand(input: DeviceCommandInput) {
    return request<ReturnType<SmartHomeDataSource['sendDeviceCommand']> extends Promise<infer T> ? T : never>(`/api/devices/${encodeURIComponent(input.device_id)}/commands`, {
      method: 'POST',
      body: JSON.stringify({ action: input.action, params: input.params }),
    });
  }

  getDeviceCommand(commandId: string) {
    return request<ReturnType<SmartHomeDataSource['getDeviceCommand']> extends Promise<infer T> ? T : never>(`/api/commands/${encodeURIComponent(commandId)}`);
  }

  getRecognitionEvents(query: Partial<HistoryQuery> = {}) {
    return request<ReturnType<SmartHomeDataSource['getRecognitionEvents']> extends Promise<infer T> ? T : never>(`/api/recognition/events${queryString(query)}`);
  }

  getCameraSnapshot() {
    return request<ReturnType<SmartHomeDataSource['getCameraSnapshot']> extends Promise<infer T> ? T : never>('/api/camera/snapshot');
  }

  async detectObjects(input: DetectionRequest) {
    const form = new FormData();
    if (input.image) form.append('image', input.image);
    else {
      const sample = await fetch(backendUrl(input.image_url || '/demo/smart-home-scene.svg')).then((response) => { if (!response.ok) throw new ApiError('读取待识别照片失败。', response.status, 'IMAGE_FETCH_ERROR'); return response.blob(); });
      form.append('image', sample, input.file_name);
    }
    form.append('width', String(input.width));
    form.append('height', String(input.height));
    form.append('source', input.source);
    return request<ReturnType<SmartHomeDataSource['detectObjects']> extends Promise<infer T> ? T : never>('/api/object-detect', { method: 'POST', body: form });
  }

  verifyFace(image: File) {
    const form = new FormData();
    form.append('image', image);
    return request<ReturnType<SmartHomeDataSource['verifyFace']> extends Promise<infer T> ? T : never>('/api/face-verify', { method: 'POST', body: form });
  }

  getPersons() {
    return request<ReturnType<SmartHomeDataSource['getPersons']> extends Promise<infer T> ? T : never>('/api/person/list');
  }

  addPerson(input: PersonInput) {
    const form = new FormData();
    form.append('name', input.name);
    form.append('user_id', input.user_id);
    if (input.face_image) form.append('face_image', input.face_image);
    return request<ReturnType<SmartHomeDataSource['addPerson']> extends Promise<infer T> ? T : never>('/api/person/add', { method: 'POST', body: form });
  }

  async deletePerson(userId: string) {
    await request<unknown>(`/api/person/delete${queryString({ user_id: userId })}`, { method: 'DELETE' });
  }

  clearTemporaryImages() {
    return request<{ count: number }>('/api/temp/clear', { method: 'DELETE' });
  }

  getLiveVision() { return request<import('@/types/contracts').LiveVision>('/api/vision/live'); }
  getAlerts() { return request<{ items: import('@/types/contracts').SystemAlert[] }>('/api/alerts'); }
  acknowledgeAlert(id: string) { return request<unknown>(`/api/alerts/${encodeURIComponent(id)}/ack`, { method: 'POST' }); }
  getModels() { return request<{ items: import('@/types/contracts').ModelStatus[] }>('/api/models'); }
  getSettings() { return request<import('@/types/contracts').RuntimeSettings>('/api/settings'); }
  updateSettings(settings: Partial<import('@/types/contracts').RuntimeSettings>) { return request<import('@/types/contracts').RuntimeSettings>('/api/settings', { method: 'PUT', body: JSON.stringify(settings) }); }
  getAuthStatus() { return request<{ write_access: boolean; authentication_required: boolean }>('/api/auth/status'); }

  subscribeEvents(callback: (event: RealtimeEvent) => void) {
    const stream = new EventSource(backendUrl('/api/stream'));
    const handlers = REALTIME_EVENTS.map((type) => {
      const handler = (message: MessageEvent) => {
        try { callback(JSON.parse(message.data) as RealtimeEvent); } catch { /* 忽略单条坏事件，快照轮询仍会兜底。 */ }
      };
      stream.addEventListener(type, handler);
      return { type, handler };
    });
    return () => {
      handlers.forEach(({ type, handler }) => stream.removeEventListener(type, handler));
      stream.close();
    };
  }
}
