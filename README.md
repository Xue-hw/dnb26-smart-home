# DnB26 Smart Home

Software workspace for the DnB26 smart home prototype. This repository covers the
Intelligent Science / IoT side of the project: data management, object
detection, face access control, GUI display, history queries, and remote control
APIs for the hardware team.

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
backend/                 FastAPI backend and hardware/vision services
frontend/                Web GUI placeholder
docs/                    Architecture, deployment, and model-selection notes
tests/                   Lightweight backend tests
data/                    Local runtime data, ignored by git
models/                  Local model weights, ignored by git
```

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
python -m backend.app
```

The default API server runs at `http://127.0.0.1:8000`.

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

Do not commit private face images, camera snapshots, database files, or model
weights. Keep them under `data/` and `models/`, which are ignored by git.
