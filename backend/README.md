# DnB26 集成后端

后端通过 FastAPI 向 Web GUI 和 Android APK 提供同一套 `/api/` 接口。MySQL 复用 `integrations/database/smarthome_setup_v2.sql` 的原有四张表，启动时幂等添加 `dnb_*` 扩展表；真实服务不会在 MySQL 故障时改用内存数据库。

## 启动

先由部署环境创建数据库并授予应用账号所需权限，再安装根目录 `requirements.txt` 和可选原生人脸依赖 `backend/requirements-face.txt`。

```bash
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1
```

摄像头所有权和活体会话均为单进程资源，当前必须使用一个 Uvicorn worker。对外访问由 Nginx 代理；无需启动 OpenCV 图形窗口。

## 配置

配置项均使用 `DNB_` 前缀：

| 环境变量 | 用途 |
|---|---|
| `DATABASE_HOST/PORT/USER/PASSWORD/NAME` | MySQL 连接，密码只放设备本地环境配置 |
| `DATABASE_INIT` | 默认 true，保留原表并创建扩展表；需要 DDL 权限 |
| `DATA_DIR` | 照片、特征和运行资料目录 |
| `CUSTOM_MODEL` / `GENERAL_MODEL` | 三类自定义 YOLO 权重与通用 COCO 权重 |
| `FACE_PREDICTOR` | dlib 68 点关键点模型 |
| `FACE_ENABLED` | 启用人脸识别 |
| `AUTO_BOOTSTRAP_FACES` | 默认 false；首次部署可显式启用，从交付照片录入授权人员 |
| `BOOTSTRAP_FACES_DIR` | 初次导入照片目录 |
| `CAMERA_ENABLED` / `CAMERA_SOURCE` | 摄像头开关、设备编号或录像路径 |
| `CAMERA_WIDTH/HEIGHT` | 摄像头请求分辨率，默认 640×480 |
| `INFERENCE_SIZE/INTERVAL` | YOLO 输入尺寸及推理间隔 |
| `HARDWARE_MODE` | mock / serial / gateway / disabled，默认 mock；双 UNO 用 gateway |
| `GATEWAY_TOKEN` | 电脑 USB 网关专用 Bearer 令牌，必须独立配置 |
| `SERIAL_PORT/BAUD` | 串口设备与波特率，默认 115200 |
| `API_TOKEN` | 管理员 Bearer 令牌，用于人员、设置、设备控制等写操作 |
| `ALLOW_UNAUTHENTICATED_WRITES` | 默认 false，仅明确隔离的演示环境才考虑开启 |
| `CORS_ORIGINS` | 逗号分隔的精确允许来源；默认包含 Capacitor 的 localhost 来源 |

例如 `DATABASE_PORT` 的完整变量名是 `DNB_DATABASE_PORT`。带密码的配置不应放入 Git、前端构建环境或聊天。

## 图像和门禁规则

- 只有一个采集线程拥有摄像头，YOLO 和人脸推理各自读取有界的最新图像，避免积压。
- YOLO 和人脸结果分别携带帧编号、采集时间；MJPEG 上只绘制对应帧的检测框。
- `/api/face-verify` 永远按静态照片处理，即使客户端提交 `source=camera` 也不能触发活体验证或开门。
- 实时会话要求授权身份、初始睁眼、连续闭眼及重新睁眼。未知身份、多人、离开、身份变化、跟踪位置显著变化、超时或采样间隔过大都会重置。
- 录像文件源标记为 replay，不能获得通行资格。摄像头断线后清除显示中的旧通行结果。
- 活体通过、控制器执行回执和物理门状态分别记录。串口 ACK 不直接制造门状态；真实门状态依赖遥测。
- 身份特征使用 `allow_pickle=False` 的 NumPy 文件，服务不反序列化交付的 `known_faces.pkl`；初次导入通过原始照片重新提取特征。

## HTTP 接口

基础 GUI 的人员、历史、抓拍、识别、设备命令等接口遵循 `integrations/gui/project/docs/GUI_API_CONTRACT.md`，并增加：

- `GET /api/auth/status`：当前令牌是否有写权限。
- `GET /api/vision/live`：最新 YOLO 和人脸结果、各自帧时间。
- `GET /api/camera/stream`：服务端带框 MJPEG，摄像头离线返回 503。
- `GET /api/models`：自定义、通用和人脸模型各自加载状态。
- `GET /api/alerts`、`POST /api/alerts/{id}/ack`：故障报警和确认。
- `GET/PUT /api/settings`：温控、门未关阈值、照片保留天数、灯泡联动和环境传感器阈值。
- `POST /api/simulation/telemetry`：仅 mock 模式且管理员认证后注入模拟遥测。

设备命令可带 `Idempotency-Key`，相同键与相同内容只执行一次。旧版 `/status`、`/people`、`/control` 是兼容早期测试的内存模拟接口，在设置管理员令牌或使用非 mock 硬件时返回 410，不能用于生产控制。

## 双 UNO 实机入口

本地已增加 `gateway` 模式，采用 UNO1／UNO2 → 电脑 USB → 香橙派 HTTP(S)，串口 9600 baud。使用 `POST /api/hardware/gateway/exchange` 和独立令牌；真实模式仅展示已安装器件，保留演示及历史兼容代码。固件、控制规则和启动方式见 [硬件整合说明](../docs/hardware-integration.md)。本轮已烧录两块 UNO 并部署 gateway 模式；逐项现场结果见联调测试表。

## 旧单串口协议

以下仅用于旧 `serial` 适配器：每行一个 UTF-8 JSON 对象，最大 8192 字节，末尾换行。双 UNO 整合固件使用上节链接中的 `DNB1` 协议与电脑网关。

```json
{"type":"heartbeat"}
{"type":"telemetry","device_id":"thermometer_1","state":{"temperature":28.5,"humidity":50}}
{"type":"telemetry","device_id":"front_door","state":{"position":"closed"}}
{"type":"ack","command_id":"由上位机给出的编号","status":"acked"}
```

上位机下发 `type=command`、`command_id`、`device_id`、`action` 和 `params`。命令只在心跳有效时发送，过期未确认的命令转为 timeout，断线恢复不自动重放开门命令。

烟雾／雨滴阈值 400／800 仅用于课程模拟的初始配置，不能当作真实浓度或安全阈值。接实机前通过设置接口按实际模块校准。温控使用开启／关闭不同阈值，减少阈值附近反复开关。

## 当前推理后端

模型路径以 `.pt` 结尾时使用 Ultralytics CPU；以 `.om` 结尾时使用项目的同步 ACL 适配器，实际后端通过 `/api/models` 的 `backend` 字段报告。板端已验证 CANN 7.0.0 / Ascend310B4 的 OM 加载、推理和多线程上下文切换；普通 ONNX 文件本身不能自动启用 NPU。

OM 要求固定 batch=1 的方形 float32 NCHW 输入、float32 `[1,4+C,N]` 原始 YOLO 输出且不内嵌 NMS。`C` 为类别数、`N` 为候选框数。旁边的同名 JSON 声明有序类别，例如 `custom640.json` 的 `{"names":["drone","fire_extinguisher","light_bulb"]}`。如果模型路径是软链接，需要将 JSON 放在解析后的实际模型旁。预处理执行固定 letterbox，后处理按类别进行 NMS，避免不同类别互相抑制。

板上转换工具见 `deploy/compile_om.sh`；API 启动通过 `deploy/start_api.sh` 引入 CANN 环境。CANN 转换使用板上的原 Python 3.9 环境，API 独立使用 Python 3.10。NPU 健康异常会作为单独报警保留；推理成功不代表健康告警已经恢复。CPU 配置与旧权重保留供显式回退。
