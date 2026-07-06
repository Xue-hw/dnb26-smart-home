import argparse
from pathlib import Path

from _project_path import add_project_root

add_project_root()

from backend.config import VisionSettings
from backend.vision.cli_utils import build_output_path, parse_class_filter
from backend.vision.yolo_detector import YoloDetector


def main() -> None:
    defaults = VisionSettings()
    parser = argparse.ArgumentParser(description="Run YOLO11n detection on one image.")
    parser.add_argument("image", help="Input image path")
    parser.add_argument("--model", default=str(defaults.model_path), help="YOLO model path")
    parser.add_argument("--conf", type=float, default=defaults.confidence, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=defaults.image_size, help="Inference image size")
    parser.add_argument("--classes", help="Comma-separated labels to keep, for example: person,car")
    parser.add_argument("--output", help="Annotated output image path")
    args = parser.parse_args()

    try:
        import cv2
    except ImportError as exc:
        raise SystemExit("opencv-python is not installed. Run: pip install -r requirements.txt") from exc

    image_path = Path(args.image)
    frame = cv2.imread(str(image_path))
    if frame is None:
        raise SystemExit(f"Could not read image: {image_path}")

    detector = YoloDetector(args.model, conf=args.conf, image_size=args.imgsz)
    detections = detector.predict(frame, class_filter=parse_class_filter(args.classes))

    for detection in detections:
        x1, y1, x2, y2 = detection.bbox_xyxy
        label = f"{detection.label} {detection.confidence:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 0), 2)
        cv2.putText(frame, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 0), 2)
        print(f"{detection.label} {detection.confidence:.3f} {detection.bbox_xyxy}")

    output_path = build_output_path(image_path, Path(args.output) if args.output else None)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), frame)
    print(f"Saved annotated image: {output_path}")


if __name__ == "__main__":
    main()
