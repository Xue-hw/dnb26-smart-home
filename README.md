# DnB26 Smart Home

Software workspace for the DnB26 smart home prototype. This repository covers the
Intelligent Science / IoT side of the project: data management, object
detection, face access control, GUI display, history queries, and remote control
APIs for the hardware team.

## 当前整合入口

真实 Web/Android GUI 位于 `integrations/gui/project/`，整合后端位于 `backend/`，保留组员的 MySQL SQL。香橙派使用 `deploy/` 下的离线与用户目录部署脚本；网页与 APK 访问同一服务。CPU 和 Ascend NPU 推理都已提供适配。

运行地址、照片与眨眼门禁规则、Arduino 串口边界、服务管理及部署现状见 [系统整合与运行说明](docs/system-integration.md)。配置项和 API 见 [后端说明](backend/README.md)，GUI 构建见 [GUI 系统说明](integrations/gui/project/docs/SYSTEM_INTEGRATION.md)，灯泡三类训练见 [训练记录](docs/bulb-model-training.md)。

双 UNO 原始交付、整合固件与电脑 USB 网关见 [硬件入口](integrations/hardware/README.md) 和 [硬件整合说明](docs/hardware-integration.md)。整合固件已烧录两块 UNO，真实 gateway 模式与新版网页已部署；未安装硬件在真实网关模式隐藏，通用代码与原 SQL 保留。

当前逐项联调见 [联调测试表](docs/联调测试表.md)，电脑网页、实体 Android APK 与硬件观察分栏记录。

## Project Scope

The course requirements ask the software team to provide:

- authorized-person management for door access
- image acquisition from the hardware model
- YOLO object detection for people, cars, and custom targets
- face recognition for access control, including at least 2 authorized and 1
  unauthorized test case
- a Web or mobile GUI for live status, history data, and remote control
- optional camera-triggered lighting, for example turning on a light when a bulb
  image is detected

## Recommended YOLO Route

Use `YOLO11n` as the main model for this project, with `YOLOv8n` as the fallback.
Both work through the modern `ultralytics` Python API and are easier to integrate
than a YOLOv5-only stack.

For the Orange Pi AIpro 20T upper computer, start with the PyTorch/CPU path until
the full pipeline is stable. Then export to ONNX and evaluate Ascend CANN/ATC
conversion if NPU acceleration is needed.

## Repository Layout

```text
backend/                 FastAPI, MySQL repository, vision and Arduino adapter
integrations/gui/project/ React/Vite Web GUI and Capacitor Android source
integrations/database/   Team SQL and original database delivery
integrations/face_recognition/ Original face delivery and registered photos
integrations/hardware/   Original UNO delivery, integrated firmware and PC USB gateway
deploy/                  Offline ARM64 deployment and service management
scripts/                 Dataset preparation, training and model utilities
deploy_export/weights/   Local checkpoints, exports and tracked experiment metadata
docs/                    Architecture, deployment and training notes
tests/                   Backend, timing, command and dataset regression tests
data/                    Local runtime/training data, ignored by git
models/                  Local general-model weights, ignored by git
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
python -m backend.app
```

The default API server runs at `http://127.0.0.1:8000`.
Configure MySQL and the `DNB_*` environment variables first; see
`backend/README.md`. The integrated production system uses MySQL and does not
replace an unavailable database with simulated in-memory data.

## YOLO11n Scripts

```powershell
python scripts/check_environment.py
python scripts/download_yolo11n.py
python scripts/detect_image.py path\to\image.jpg --classes person,car
python scripts/detect_camera.py --camera 0 --classes person
python scripts/export_yolo11n_onnx.py
```

Use `models/yolo11n.pt` as the default weight file. Keep later optimized ONNX,
OM, TensorRT, or quantized exports under `models/` as local artifacts.

## Runtime Data Policy

The original face delivery is retained under `integrations/` according to the
user's explicit upload authorization. Newly captured images, feature vectors,
database files, deployment credentials and model binaries stay in ignored local
runtime/artifact directories or the board's private `shared/` directory.
