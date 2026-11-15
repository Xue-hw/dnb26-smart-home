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

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
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
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: init.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init.headers },
    });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof payload === 'object' && payload ? payload.detail || payload.message || payload.msg : payload;
      throw new ApiError(typeof detail === 'string' ? detail : `HTTP ${response.status}`, response.status, 'HTTP_ERROR', payload);
    }
    return payload as T;
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
      const sample = await fetch(input.image_url || '/demo/smart-home-scene.svg').then((response) => response.blob());
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

  subscribeEvents(callback: (event: RealtimeEvent) => void) {
    const stream = new EventSource(`${API_BASE}/api/stream`);
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
