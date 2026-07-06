import argparse

from _project_path import add_project_root

add_project_root()

from backend.config import VisionSettings
from backend.vision.cli_utils import parse_class_filter
from backend.vision.yolo_detector import YoloDetector


def main() -> None:
    defaults = VisionSettings()
    parser = argparse.ArgumentParser(description="Run YOLO11n detection on a camera stream.")
    parser.add_argument("--camera", default="0", help="Camera index or video path")
    parser.add_argument("--model", default=str(defaults.model_path), help="YOLO model path")
    parser.add_argument("--conf", type=float, default=defaults.confidence, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=defaults.image_size, help="Inference image size")
    parser.add_argument("--classes", help="Comma-separated labels to keep")
    parser.add_argument("--width", type=int, default=640, help="Capture width")
    parser.add_argument("--height", type=int, default=480, help="Capture height")
    parser.add_argument("--no-window", action="store_true", help="Run without opening a display window")
    args = parser.parse_args()

    try:
        import cv2
    except ImportError as exc:
        raise SystemExit("opencv-python is not installed. Run: pip install -r requirements.txt") from exc

    source = int(args.camera) if args.camera.isdigit() else args.camera
    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera/video source: {args.camera}")

    detector = YoloDetector(args.model, conf=args.conf, image_size=args.imgsz)
    class_filter = parse_class_filter(args.classes)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            detections = detector.predict(frame, class_filter=class_filter)
            print(", ".join(f"{item.label}:{item.confidence:.2f}" for item in detections) or "no detections")

            if not args.no_window:
                for detection in detections:
                    x1, y1, x2, y2 = detection.bbox_xyxy
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 180, 0), 2)
                    cv2.putText(frame, detection.label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 180, 0), 2)
                cv2.imshow("DnB26 YOLO11n", frame)
                if cv2.waitKey(1) == 27:
                    break
    finally:
        cap.release()
        if not args.no_window:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
