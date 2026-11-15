export type DataMode = 'mock' | 'http';
export type DataFreshness = 'live' | 'mock' | 'cached' | 'unknown';
export type OnlineStatus = 'online' | 'offline' | 'unknown';
export type CommandStatus = 'pending' | 'acked' | 'failed' | 'timeout';
export type DeviceKind = 'door' | 'window' | 'light' | 'fan' | 'air_conditioner' | 'lock';
export type SensorMetric = 'temperature' | 'humidity';
export type RecognitionType = 'object' | 'face';
export type RecognitionSource = 'demo' | 'upload' | 'camera';

export interface SystemStatus {
  mode: DataMode;
  version: string;
  backend: OnlineStatus;
  database: OnlineStatus;
  camera: OnlineStatus;
  hardware: OnlineStatus;
  model: string;
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
}

export interface DeviceEvent {
  event_id: string;
  device_id: string;
  device_name: string;
  action: string;
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
  command_id: string;
  status: CommandStatus;
  requested_at: string;
  acked_at?: string;
  error_message?: string;
}

export interface Detection {
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
  addPerson(input: PersonInput): Promise<Person>;
  deletePerson(userId: string): Promise<void>;
  clearTemporaryImages(): Promise<{ count: number }>;
  subscribeEvents(callback: (event: RealtimeEvent) => void): () => void;
}
