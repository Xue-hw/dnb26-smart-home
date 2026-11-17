export type DataMode = 'mock' | 'http';
export type DataFreshness = 'live' | 'mock' | 'cached' | 'unknown';
export type OnlineStatus = 'online' | 'offline' | 'unknown';
export type CommandStatus = 'pending' | 'acked' | 'failed' | 'timeout';
export type DeviceKind = 'door' | 'window' | 'light' | 'fan' | 'air_conditioner' | 'lock' | 'voice';
export type SensorMetric = 'temperature' | 'humidity' | 'smoke' | 'rain' | 'light';
export type RecognitionType = 'object' | 'face';
export type RecognitionSource = 'demo' | 'upload' | 'camera';

export interface ServerClock {
  timestamp: number;
  receivedAt: number;
  browserOffset: number;
}

export interface SystemStatus {
  mode: DataMode;
  version: string;
  backend: OnlineStatus;
  database: OnlineStatus;
  camera: OnlineStatus;
  hardware: OnlineStatus;
  model: string;
  hardware_mode?: string;
  hardware_boards?: Record<string, {
    status: OnlineStatus;
    message: string;
    capabilities: string[];
    temperature_on?: number;
    temperature_off?: number;
    temperature_config_synced?: boolean;
  }>;
  services?: Record<string, unknown>;
  server_time: string;
  message: string;
}

export interface SensorReading {
  id: string;
  device_id: string;
  metric: SensorMetric;
  value: number;
  unit: string;
  measured_at: string;
  status: OnlineStatus;
}

export interface DeviceState {
  device_id: string;
  name: string;
  kind: DeviceKind;
  state: Record<string, boolean | number | string>;
  status: OnlineStatus;
  updated_at: string;
  board_id?: string;
  capabilities?: string[];
}

export interface DeviceEvent {
  event_id: string;
  device_id: string;
  device_name: string;
  action: string;
  uid?: string;
  command?: number;
  state: Record<string, boolean | number | string>;
  source: string;
  command_id?: string;
  occurred_at: string;
}

export interface DashboardSnapshot {
  freshness: DataFreshness;
  server_time: string;
  sensors: SensorReading[];
  devices: DeviceState[];
  recent_events: DeviceEvent[];
}

export interface HistoryQuery {
  start: string;
  end: string;
  device_id?: string;
  metric?: SensorMetric;
  page?: number;
  page_size?: number;
}

export interface SensorPoint {
  ts: string;
  value: number;
}

export interface SensorSeries {
  metric: SensorMetric;
  unit: string;
  points: SensorPoint[];
  aggregated: boolean;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DeviceCommandInput {
  device_id: string;
  action: 'set' | 'toggle';
  params: Record<string, boolean | number | string>;
}

export interface DeviceCommand extends DeviceCommandInput {
  source?: string;
  command_id: string;
  status: CommandStatus;
  requested_at: string;
  acked_at?: string;
  error_message?: string;
}

export interface Detection {
  model?: 'general' | 'custom' | string;
  label: string;
  label_zh: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface DetectionRequest {
  image: File | null;
  image_url?: string;
  file_name: string;
  width: number;
  height: number;
  source: RecognitionSource;
}

export interface DetectionResult {
  event_id: string;
  image_url: string | null;
  width: number;
  height: number;
  detections: Detection[];
  count: number;
  inference_ms: number;
  mode: DataMode;
  message: string;
}

export interface FaceVerifyResult {
  event_id: string;
  matched: boolean;
  identity_matched?: boolean;
  liveness_status?: 'pending' | 'passed' | 'timeout' | 'unavailable' | 'not_applicable' | 'failed';
  identity_recheck?: boolean;
  verification_remaining_seconds?: number;
  match_threshold?: number;
  access_granted?: boolean;
  command_id?: string | null;
  reason?: string;
  similarity: number;
  user_id: string | null;
  user_name: string;
  face_boxes: [number, number, number, number][];
  message: string;
  mode: DataMode;
}

export interface RecognitionEvent {
  event_id: string;
  type: RecognitionType;
  source: RecognitionSource;
  image_url: string | null;
  file_name: string;
  result_summary: string;
  detections: Detection[];
  matched?: boolean;
  person_id?: string | null;
  similarity?: number;
  occurred_at: string;
}

export interface Person {
  user_id: string;
  name: string;
  avatar_url: string | null;
  created_at: string;
  feature_version: string;
}

export interface PersonInput {
  user_id: string;
  name: string;
  face_image: File | null;
}

export interface PersonEnrollment {
  user_id: string;
  status: 'ready' | 'not_found' | 'inactive' | 'feature_missing' | 'feature_invalid' | 'model_unavailable' | 'not_loaded' | 'simulated';
  active: boolean;
  loaded: boolean;
  feature_status: string;
  feature_version: string | null;
  model_status: string;
  checked_at: string;
  message: string;
}

export interface CameraSnapshot {
  /** Optional integration fields; absence must not imply saved. */
  saved?: boolean;
  archive_url?: string;
  camera_id: string;
  image_url: string;
  captured_at: string;
  status: OnlineStatus;
  message: string;
}

export type RealtimeEventType =
  | 'sensor.updated'
  | 'device.state.changed'
  | 'command.updated'
  | 'recognition.created'
  | 'camera.status.changed'
  | 'system.status.changed';

export interface RealtimeEvent<T = unknown> {
  event_id: string;
  type: RealtimeEventType;
  occurred_at: string;
  source: DataMode;
  payload: T;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(message: string, status = 500, code = 'API_ERROR', details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface SmartHomeDataSource {
  getSystemStatus(): Promise<SystemStatus>;
  getDashboardSnapshot(): Promise<DashboardSnapshot>;
  getSensorHistory(query: HistoryQuery): Promise<SensorSeries[]>;
  getDeviceEvents(query: HistoryQuery): Promise<Paginated<DeviceEvent>>;
  sendDeviceCommand(input: DeviceCommandInput): Promise<DeviceCommand>;
  getDeviceCommand(commandId: string): Promise<DeviceCommand>;
  getRecognitionEvents(query?: Partial<HistoryQuery>): Promise<Paginated<RecognitionEvent>>;
  getCameraSnapshot(): Promise<CameraSnapshot>;
  detectObjects(request: DetectionRequest): Promise<DetectionResult>;
  verifyFace(image: File): Promise<FaceVerifyResult>;
  getPersons(): Promise<Person[]>;
  getPersonEnrollment(userId: string): Promise<PersonEnrollment>;
  addPerson(input: PersonInput): Promise<Person>;
  deletePerson(userId: string): Promise<void>;
  clearTemporaryImages(): Promise<{ count: number }>;
  getLiveVision(): Promise<LiveVision>;
  getAlerts(): Promise<{ items: SystemAlert[] }>;
  acknowledgeAlert(id: string): Promise<unknown>;
  getModels(): Promise<{ items: ModelStatus[] }>;
  getSettings(): Promise<RuntimeSettings>;
  updateSettings(settings: Partial<RuntimeSettings>): Promise<RuntimeSettings>;
  getAuthStatus(): Promise<{ write_access: boolean; authentication_required: boolean }>;
  subscribeEvents(callback: (event: RealtimeEvent) => void): () => void;
}

export interface LiveFace {
  user_id: string | null;
  user_name: string;
  identity_matched: boolean;
  liveness_status: FaceVerifyResult['liveness_status'];
  identity_recheck?: boolean;
  verification_remaining_seconds?: number;
  similarity?: number;
  match_threshold?: number;
  access_granted: boolean;
  command_id?: string | null;
  reason?: string;
  bbox?: [number, number, number, number];
}
export interface FaceCooldown {
  active: boolean;
  phase: 'idle' | 'waiting_open' | 'waiting_close' | 'unknown';
  command_id: string | null;
  generation?: number;
}
export interface LiveVision {
  face_cooldown?: FaceCooldown;
  server_time?: string;
  frame_id: number;
  captured_at: string | null;
  face_captured_at?: string | null;
  objects: Detection[];
  faces: LiveFace[];
  width: number;
  height: number;
  camera_status: OnlineStatus;
  inference_ms?: number;
  fps?: number;
  message?: string;
}
export interface SystemAlert {
  id: string;
  code: string;
  severity: 'info' | 'warning' | 'critical' | 'error';
  message: string;
  active: boolean;
  acknowledged: boolean;
  created_at: string;
  resolved_at?: string | null;
}
export interface ModelStatus {
  name: string;
  status: string;
  classes: string[];
  message?: string;
}
export interface RuntimeSettings {
  temperature_on: number;
  temperature_off: number;
  door_open_seconds: number;
  bulb_linkage: boolean;
  retention_days: number;
}
