# GUI 数据接口契约

版本：`GUI API Contract v1`
对应类型：`src/types/contracts.ts`
页面唯一依赖：`SmartHomeDataSource`

## 1. 责任边界

GUI 不直接访问 GPIO、串口、MQTT、摄像头设备节点或模型文件。硬件组和模型组通过后端提供统一 HTTP 数据，GUI 只负责展示、查询、命令提交和状态反馈。

默认 Mock 与真实 HTTP 实现同一接口。后端字段变化应优先在 `httpDataSource.ts` 内适配，避免把后端特殊字段扩散到页面。

## 2. REST 接口映射

| DataSource 方法 | HTTP 方法与路径 | 说明 |
|---|---|---|
| `getSystemStatus` | `GET /api/system/status` | 后端、数据库、摄像头、硬件、模型状态 |
| `getDashboardSnapshot` | `GET /api/dashboard/snapshot` | 首页最新快照 |
| `getSensorHistory` | `GET /api/sensors/history` | `start/end/metric` 查询序列 |
| `getDeviceEvents` | `GET /api/devices/events` | `start/end/device_id/page/page_size` |
| `sendDeviceCommand` | `POST /api/devices/{device_id}/commands` | body：`action`、`params` |
| `getDeviceCommand` | `GET /api/commands/{command_id}` | 查询 pending/acked/failed/timeout |
| `getRecognitionEvents` | `GET /api/recognition/events` | 识别历史和图片 URL |
| `getCameraSnapshot` | `GET /api/camera/snapshot` | 抓帧 URL、时间、状态 |
| `detectObjects` | `POST /api/object-detect` | multipart：`image/width/height/source` |
| `verifyFace` | `POST /api/face-verify` | multipart：`image` |
| `getPersons` | `GET /api/person/list` | 人员数组 |
| `addPerson` | `POST /api/person/add` | multipart：`name/user_id/face_image` |
| `deletePerson` | `DELETE /api/person/delete?user_id=...` | 成功后才从 GUI 移除 |
| `clearTemporaryImages` | `DELETE /api/temp/clear` | 返回 `{ count }` |
| `subscribeEvents` | `GET /api/stream` | SSE 命名事件 |

真实后端可以保留旧路径，但响应应映射为本契约。若沿用旧后端的 `{code,data}` 包装，应在 Adapter 内解包，不让页面判断多种返回层级。

## 3. 核心字段约定

### DashboardSnapshot

- `freshness`：`live/mock/cached/unknown`，GUI 据此显示实时或演示标记。
- `server_time`：ISO 8601 时间。
- `sensors`：每个指标的最新值，含 `metric/value/unit/measured_at/status`。
- `devices`：`device_id/name/kind/state/status/updated_at`。
- `recent_events`：最近设备事件。

设备 `kind` 当前为 `door/window/light/fan/air_conditioner/lock`。`state` 常用键：

- 门窗：`position: open|closed`
- 灯：`power`、`brightness`
- 风扇/空调：`power`
- 空调：`target_temperature`
- 门锁：`locked`

### DeviceCommand

`command_id` 是查询和审计的唯一标识。`pending` 只表示命令已提交，GUI 不得将其显示为硬件执行成功；只有 `acked` 才显示确认。失败和超时必须保留 `error_message`。

### DetectionResult

`bbox` 是 `[x1,y1,x2,y2]`，使用原图像素坐标，不是 0～1 归一化坐标。GUI Canvas 按原图像素绘制，再通过 CSS 等比显示。

`label` 为模型原始英文类别，`label_zh` 为 GUI 显示名。`mode=mock` 时必须保留演示提示。

### RecognitionEvent

保存 `image_url` 和元数据，不要求 GUI 把 base64 原图写入 localStorage。上传图片不能持久化时允许 `image_url=null`，GUI 会显示占位图并明确说明。

### 时间

查询输入由 GUI 从本地 `datetime-local` 转为 ISO UTC 字符串。后端也返回 ISO 时间，GUI 按浏览器本地时区显示。

### 错误

HTTP 非 2xx 可返回 FastAPI `detail`，或 `message/msg`。Adapter 统一转成 `ApiError(message,status,code,details)`。页面展示具体错误，删除人员失败不得本地隐藏。

## 4. SSE 事件

事件名为：

- `sensor.updated`
- `device.state.changed`
- `command.updated`
- `recognition.created`
- `camera.status.changed`
- `system.status.changed`

事件 data 使用 JSON：

```json
{
  "event_id": "event_xxx",
  "type": "device.state.changed",
  "occurred_at": "2026-11-13T08:00:00.000Z",
  "source": "http",
  "payload": {}
}
```

GUI 收到设备或系统事件后重新拉取快照，避免只凭推送增量造成状态不一致。另有 30 秒轮询兜底，SSE 断线不影响最终状态恢复。

## 5. 接入步骤

1. 后端先实现 `system/status`、`dashboard/snapshot` 两个只读接口。
2. 对照 `contracts.ts` 返回字段，用 HTTP 模式验证首页。
3. 接入历史、人员和识别只读接口。
4. 在硬件测试环境单独启用设备命令，确认 pending/acked/failed/timeout。
5. 最后接入 SSE；未接入前 GUI 仍可轮询运行。

## 6. Mock 自测范围

Mock 模式自测全部 15 项接口，包括新增并删除临时人员、产生一条保持灯原状态的命令、识别事件和临时文件清理。HTTP 模式只执行只读检查，避免误触真实硬件。
