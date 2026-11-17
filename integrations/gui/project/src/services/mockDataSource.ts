import {
  ApiError,
  type CameraSnapshot,
  type DashboardSnapshot,
  type Detection,
  type DetectionRequest,
  type DetectionResult,
  type DeviceCommand,
  type DeviceCommandInput,
  type DeviceEvent,
  type DeviceState,
  type FaceVerifyResult,
  type HistoryQuery,
  type Paginated,
  type Person,
  type PersonInput,
  type RealtimeEvent,
  type RecognitionEvent,
  type SensorReading,
  type SensorSeries,
  type SmartHomeDataSource,
  type SystemStatus,
} from '@/types/contracts';

const DB_KEY = 'dnb26_gui_mock_db_v1';
const DB_VERSION = 1;

interface MockDatabase {
  meta: { version: number; created_at: string; updated_at: string };
  sensors: SensorReading[];
  devices: DeviceState[];
  device_events: DeviceEvent[];
  commands: DeviceCommand[];
  recognition_events: RecognitionEvent[];
  persons: Person[];
  temp_uploads: string[];
}

type Listener = (event: RealtimeEvent) => void;
const listeners = new Set<Listener>();
let memoryDatabase: MockDatabase | null = null;

const makeId = (prefix: string) =>
  `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
const iso = (time: number) => new Date(time).toISOString();
function voiceDevice(updatedAt = new Date().toISOString()): DeviceState {
  return { device_id: 'voice_control', name: '语音控制', kind: 'voice', state: { power: true }, status: 'online', updated_at: updatedAt };
}
const wait = (ms = 240) => new Promise((resolve) => window.setTimeout(resolve, ms));

function sampleDetections(width = 960, height = 540): Detection[] {
  const boxes: Array<[number, number, number, number]> = [
    [0.1, 0.2, 0.3, 0.88],
    [0.4, 0.49, 0.76, 0.85],
    [0.78, 0.12, 0.91, 0.39],
  ];
  const labels = [
    ['person', '人员', 0.96],
    ['car', '车辆', 0.92],
    ['light_bulb', '灯泡', 0.89],
  ] as const;
  return labels.map(([label, label_zh, confidence], index) => ({
    label,
    label_zh,
    confidence,
    bbox: [
      Math.round(boxes[index][0] * width),
      Math.round(boxes[index][1] * height),
      Math.round(boxes[index][2] * width),
      Math.round(boxes[index][3] * height),
    ],
  }));
}

function createSeedDatabase(): MockDatabase {
  const now = Date.now();
  const sensors: SensorReading[] = [];
  for (let index = 48; index >= 0; index -= 1) {
    const time = now - index * 30 * 60 * 1000;
    const progress = (48 - index) / 48;
    sensors.push({
      id: `temp_${time}`,
      device_id: 'sensor_room_01',
      metric: 'temperature',
      value: Number((23.2 + Math.sin(progress * Math.PI * 3) * 2.1 + progress * 0.8).toFixed(1)),
      unit: '°C',
      measured_at: iso(time),
      status: 'online',
    });
    sensors.push({
      id: `hum_${time}`,
      device_id: 'sensor_room_01',
      metric: 'humidity',
      value: Math.round(51 + Math.cos(progress * Math.PI * 2) * 8),
      unit: '%RH',
      measured_at: iso(time),
      status: 'online',
    });
  }

  const devices: DeviceState[] = [
    { device_id: 'door_01', name: '入户门', kind: 'door', state: { position: 'closed' }, status: 'online', updated_at: iso(now - 8 * 60 * 1000) },
    { device_id: 'window_01', name: '客厅窗', kind: 'window', state: { position: 'closed' }, status: 'online', updated_at: iso(now - 18 * 60 * 1000) },
    { device_id: 'light_01', name: '客厅灯', kind: 'light', state: { power: true, brightness: 68 }, status: 'online', updated_at: iso(now - 5 * 60 * 1000) },
    { device_id: 'fan_01', name: '循环风扇', kind: 'fan', state: { power: false }, status: 'online', updated_at: iso(now - 30 * 60 * 1000) },
    { device_id: 'ac_01', name: '空调', kind: 'air_conditioner', state: { power: false, target_temperature: 26 }, status: 'online', updated_at: iso(now - 42 * 60 * 1000) },
    { device_id: 'lock_01', name: '门禁锁', kind: 'lock', state: { locked: true }, status: 'online', updated_at: iso(now - 8 * 60 * 1000) },
    voiceDevice(iso(now)),
  ];

  const deviceEvents: DeviceEvent[] = devices.slice(0, 4).map((device, index) => ({
    event_id: `seed_event_${index}`,
    device_id: device.device_id,
    device_name: device.name,
    action: '演示初始状态',
    state: { ...device.state },
    source: 'mock-seed',
    occurred_at: device.updated_at,
  }));

  const recognitionEvents: RecognitionEvent[] = [{
    event_id: 'seed_recognition_01',
    type: 'object',
    source: 'demo',
    image_url: '/demo/smart-home-scene.svg',
    file_name: 'smart-home-scene.svg',
    result_summary: '预置场景：人员、车辆、灯泡（Mock）',
    detections: sampleDetections(),
    occurred_at: iso(now - 12 * 60 * 1000),
  }];

  return {
    meta: { version: DB_VERSION, created_at: iso(now), updated_at: iso(now) },
    sensors,
    devices,
    device_events: deviceEvents,
    commands: [],
    recognition_events: recognitionEvents,
    persons: [
      { user_id: 'DNB001', name: '张同学', avatar_url: null, created_at: iso(now - 2 * 86400000), feature_version: 'mock-v1' },
      { user_id: 'DNB002', name: '李同学', avatar_url: null, created_at: iso(now - 86400000), feature_version: 'mock-v1' },
    ],
    temp_uploads: [],
  };
}

function loadDatabase(): MockDatabase {
  if (memoryDatabase) return memoryDatabase;
  try {
    const raw = window.localStorage.getItem(DB_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as MockDatabase;
      if (parsed.meta?.version === DB_VERSION) {
        if (!parsed.devices.some(device => device.device_id === 'voice_control')) parsed.devices.push(voiceDevice());
        memoryDatabase = parsed;
        return parsed;
      }
    }
  } catch {
    // 数据损坏时回退为全新演示库，页面仍可使用。
  }
  memoryDatabase = createSeedDatabase();
  saveDatabase(memoryDatabase);
  return memoryDatabase;
}

function saveDatabase(database: MockDatabase) {
  database.meta.updated_at = new Date().toISOString();
  memoryDatabase = database;
  try {
    window.localStorage.setItem(DB_KEY, JSON.stringify(database));
  } catch {
    throw new ApiError('浏览器本地存储空间不足，请清理演示数据后重试。', 507, 'STORAGE_FULL');
  }
}

function mutate<T>(operation: (database: MockDatabase) => T): T {
  const database = loadDatabase();
  const result = operation(database);
  saveDatabase(database);
  return result;
}

function emit<T>(type: RealtimeEvent['type'], payload: T) {
  const event: RealtimeEvent<T> = {
    event_id: makeId('event'),
    type,
    occurred_at: new Date().toISOString(),
    source: 'mock',
    payload,
  };
  listeners.forEach((listener) => listener(event));
}

function paginate<T>(items: T[], page = 1, pageSize = 50): Paginated<T> {
  const safePageSize = Math.min(Math.max(pageSize, 1), 200);
  return {
    items: items.slice((page - 1) * safePageSize, page * safePageSize),
    total: items.length,
    page,
    page_size: safePageSize,
  };
}

function inRange(value: string, query: HistoryQuery) {
  const time = new Date(value).getTime();
  return time >= new Date(query.start).getTime() && time <= new Date(query.end).getTime();
}

export class MockDataSource implements SmartHomeDataSource {
  async getSystemStatus(): Promise<SystemStatus> {
    await wait(120);
    const db = loadDatabase();
    return {
      mode: 'mock',
      version: 'GUI v1.2.0 / Mock API v1',
      backend: 'online',
      database: 'online',
      camera: 'unknown',
      hardware: 'unknown',
      model: '预置结果检测器（非真实 YOLO）',
      server_time: new Date().toISOString(),
      message: `纯前端演示 · ${db.persons.length} 名人员 · ${db.recognition_events.length} 条识别记录`,
    };
  }

  async getDashboardSnapshot(): Promise<DashboardSnapshot> {
    await wait();
    const db = loadDatabase();
    const sensors = (['temperature', 'humidity'] as const).map((metric) =>
      db.sensors.filter((item) => item.metric === metric).sort((a, b) => b.measured_at.localeCompare(a.measured_at))[0],
    );
    return {
      freshness: 'mock',
      server_time: new Date().toISOString(),
      sensors,
      devices: db.devices.map((device) => ({ ...device, state: { ...device.state } })),
      recent_events: [...db.device_events].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at)).slice(0, 5),
    };
  }

  async getSensorHistory(query: HistoryQuery): Promise<SensorSeries[]> {
    await wait();
    const metrics = query.metric ? [query.metric] : ['temperature', 'humidity'] as const;
    return metrics.map((metric) => {
      const points = loadDatabase().sensors
        .filter((item) => item.metric === metric && inRange(item.measured_at, query))
        .sort((a, b) => a.measured_at.localeCompare(b.measured_at))
        .map((item) => ({ ts: item.measured_at, value: item.value }));
      return { metric, unit: metric === 'temperature' ? '°C' : '%RH', points, aggregated: false };
    });
  }

  async getDeviceEvents(query: HistoryQuery): Promise<Paginated<DeviceEvent>> {
    await wait();
    const items = loadDatabase().device_events
      .filter((item) => inRange(item.occurred_at, query) && (!query.device_id || item.device_id === query.device_id))
      .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
    return paginate(items, query.page, query.page_size);
  }

  async sendDeviceCommand(input: DeviceCommandInput): Promise<DeviceCommand> {
    const device = loadDatabase().devices.find((item) => item.device_id === input.device_id);
    if (!device) throw new ApiError('设备不存在。', 404, 'DEVICE_NOT_FOUND');
    const pending: DeviceCommand = {
      ...input,
      command_id: makeId('cmd'),
      status: 'pending',
      requested_at: new Date().toISOString(),
    };
    mutate((db) => { db.commands.unshift(pending); });
    emit('command.updated', pending);
    await wait(520);
    const acked = mutate((db) => {
      const target = db.devices.find((item) => item.device_id === input.device_id)!;
      const nextState = input.action === 'set' ? { ...target.state, ...input.params } : { ...target.state };
      if (input.action === 'toggle') {
        if ('position' in nextState) nextState.position = nextState.position === 'open' ? 'closed' : 'open';
        else if ('locked' in nextState) nextState.locked = !nextState.locked;
        else nextState.power = !nextState.power;
      }
      target.state = nextState;
      target.updated_at = new Date().toISOString();
      const command = db.commands.find((item) => item.command_id === pending.command_id)!;
      command.status = 'acked';
      command.acked_at = target.updated_at;
      db.device_events.unshift({
        event_id: makeId('device'),
        device_id: target.device_id,
        device_name: target.name,
        action: input.action === 'toggle' ? '切换状态' : '设置状态',
        state: { ...nextState },
        source: 'gui-demo',
        command_id: command.command_id,
        occurred_at: target.updated_at,
      });
      return command;
    });
    emit('command.updated', acked);
    emit('device.state.changed', { device_id: input.device_id, command_id: acked.command_id });
    return { ...acked };
  }

  async getDeviceCommand(commandId: string): Promise<DeviceCommand> {
    await wait(100);
    const command = loadDatabase().commands.find((item) => item.command_id === commandId);
    if (!command) throw new ApiError('命令不存在。', 404, 'COMMAND_NOT_FOUND');
    return { ...command };
  }

  async getRecognitionEvents(query: Partial<HistoryQuery> = {}): Promise<Paginated<RecognitionEvent>> {
    await wait();
    const items = loadDatabase().recognition_events
      .filter((item) => {
        if (!query.start || !query.end) return true;
        return inRange(item.occurred_at, query as HistoryQuery);
      })
      .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
    return paginate(items, query.page, query.page_size);
  }

  async getCameraSnapshot(): Promise<CameraSnapshot> {
    await wait();
    return {
      camera_id: 'demo_camera_01',
      image_url: '/demo/camera-preview.svg',
      captured_at: new Date().toISOString(),
      status: 'unknown',
      message: '预置摄像头画面，仅验证图片接口，不是实时视频。',
    };
  }

  async detectObjects(request: DetectionRequest): Promise<DetectionResult> {
    await wait(720);
    const detections = sampleDetections(request.width, request.height);
    const event: RecognitionEvent = {
      event_id: makeId('recognition'),
      type: 'object',
      source: request.source,
      image_url: request.image ? null : request.image_url || '/demo/smart-home-scene.svg',
      file_name: request.file_name,
      result_summary: `${detections.length} 个预置目标：人员、车辆、灯泡（Mock）`,
      detections,
      occurred_at: new Date().toISOString(),
    };
    mutate((db) => {
      db.recognition_events.unshift(event);
      if (request.image) db.temp_uploads.push(request.file_name);
    });
    emit('recognition.created', event);
    return {
      event_id: event.event_id,
      image_url: event.image_url,
      width: request.width,
      height: request.height,
      detections,
      count: detections.length,
      inference_ms: 186,
      mode: 'mock',
      message: '接口与 Canvas 联调成功；结果为预置数据，未运行真实模型。',
    };
  }

  async verifyFace(image: File): Promise<FaceVerifyResult> {
    await wait(650);
    const event: RecognitionEvent = {
      event_id: makeId('recognition'),
      type: 'face',
      source: 'upload',
      image_url: null,
      file_name: image.name,
      result_summary: 'Mock 人脸接口已连通，未执行真实特征比对',
      detections: [],
      matched: false,
      person_id: null,
      similarity: 0,
      occurred_at: new Date().toISOString(),
    };
    mutate((db) => {
      db.recognition_events.unshift(event);
      db.temp_uploads.push(image.name);
    });
    emit('recognition.created', event);
    return {
      event_id: event.event_id,
      matched: false,
      similarity: 0,
      user_id: null,
      user_name: '未执行真实比对',
      face_boxes: [],
      message: '人脸接口已连通；演示版不运行 InsightFace，也不触发开门。',
      mode: 'mock',
    };
  }

  async getPersons(): Promise<Person[]> {
    await wait();
    return [...loadDatabase().persons].sort((a, b) => a.user_id.localeCompare(b.user_id));
  }

  async getPersonEnrollment(userId: string): Promise<import('@/types/contracts').PersonEnrollment> {
    await wait();
    const person = loadDatabase().persons.find(item => item.user_id === userId);
    return { user_id: userId, status: 'simulated', active: false, loaded: false, feature_status: 'not_enrolled',
      feature_version: person?.feature_version ?? null, model_status: 'mock', checked_at: new Date().toISOString(),
      message: '模拟资料已保存；演示模式没有录入真实人脸特征。' };
  }

  async addPerson(input: PersonInput): Promise<Person> {
    await wait(420);
    if (!input.name.trim() || !input.user_id.trim()) throw new ApiError('姓名和人员 ID 不能为空。', 400, 'INVALID_INPUT');
    if (loadDatabase().persons.some((item) => item.user_id === input.user_id.trim())) {
      throw new ApiError('该人员 ID 已存在。', 400, 'DUPLICATE_PERSON');
    }
    const person: Person = {
      user_id: input.user_id.trim(),
      name: input.name.trim(),
      avatar_url: null,
      created_at: new Date().toISOString(),
      feature_version: 'mock-v1（仅保存元数据）',
    };
    mutate((db) => { db.persons.push(person); });
    return { ...person };
  }

  async deletePerson(userId: string): Promise<void> {
    await wait(360);
    mutate((db) => {
      const index = db.persons.findIndex((item) => item.user_id === userId);
      if (index < 0) throw new ApiError('该人员不存在。', 404, 'PERSON_NOT_FOUND');
      db.persons.splice(index, 1);
    });
  }

  async clearTemporaryImages(): Promise<{ count: number }> {
    await wait();
    const count = mutate((db) => {
      const size = db.temp_uploads.length;
      db.temp_uploads = [];
      return size;
    });
    return { count };
  }

  async getLiveVision(): Promise<import('@/types/contracts').LiveVision> { return { frame_id: 0, captured_at: null, objects: [], faces: [], width: 640, height: 480, camera_status: 'unknown', message: '演示模式没有真实摄像头与活体结果' }; }
  async getAlerts(): Promise<{ items: import('@/types/contracts').SystemAlert[] }> { return { items: [] }; }
  async acknowledgeAlert(_id: string) { return { id: _id, acknowledged: true }; }
  async getModels() { return { items: [{ name: '演示模型（非推理）', status: 'mock', classes: [] as string[] }] }; }
  async getSettings() { return { temperature_on: 30, temperature_off: 28, door_open_seconds: 30, bulb_linkage: false, retention_days: 7 }; }
  async updateSettings(settings: Partial<import('@/types/contracts').RuntimeSettings>) { return { ...await this.getSettings(), ...settings }; }
  async getAuthStatus() { return { write_access: true, authentication_required: false }; }
  subscribeEvents(callback: Listener): () => void {
    listeners.add(callback);
    return () => listeners.delete(callback);
  }
}

export function resetMockDatabase() {
  memoryDatabase = createSeedDatabase();
  saveDatabase(memoryDatabase);
  emit('system.status.changed', { reset: true });
}

export function getMockDatabaseStats() {
  const db = loadDatabase();
  return {
    sensor_readings: db.sensors.length,
    devices: db.devices.length,
    device_events: db.device_events.length,
    commands: db.commands.length,
    recognition_events: db.recognition_events.length,
    persons: db.persons.length,
    temporary_uploads: db.temp_uploads.length,
    storage_bytes: new Blob([JSON.stringify(db)]).size,
    created_at: db.meta.created_at,
    updated_at: db.meta.updated_at,
  };
}
