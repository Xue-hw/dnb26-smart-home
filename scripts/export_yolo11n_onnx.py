import argparse
from pathlib import Path

from _project_path import add_project_root

add_project_root()

from backend.config import VisionSettings


def main() -> None:
    defaults = VisionSettings()
    parser = argparse.ArgumentParser(description="Export YOLO11n weights to ONNX.")
    parser.add_argument("--model", default=str(defaults.model_path), help="YOLO model path")
    parser.add_argument("--imgsz", type=int, default=defaults.image_size, help="Export image size")
    parser.add_argument("--opset", type=int, default=12, help="ONNX opset")
    parser.add_argument("--dynamic", action="store_true", help="Export with dynamic input shape")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model not found: {model_path}. Run scripts/download_yolo11n.py first.")

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("ultralytics is not installed. Run: pip install -r requirements.txt") from exc

    model = YOLO(str(model_path))
    exported = model.export(format="onnx", imgsz=args.imgsz, opset=args.opset, dynamic=args.dynamic)
    print(f"Exported ONNX model: {exported}")


if __name__ == "__main__":
    main()
