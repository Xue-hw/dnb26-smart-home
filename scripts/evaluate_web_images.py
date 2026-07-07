"""批量运行联合 YOLO 模型，对网络测试图片生成标注图和检测结果表。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ultralytics import YOLO


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def iter_images(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(path for path in source.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trained drone/fire-extinguisher detector on web images.")
    parser.add_argument("--model", required=True, help="Path to trained YOLO model")
    parser.add_argument("--source", required=True, help="Image file or flat image directory")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size")
    args = parser.parse_args()

    source = Path(args.source)
    output_dir = Path(args.output)
    annotated_dir = output_dir / "annotated"
    annotated_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    rows: list[dict[str, object]] = []
    image_paths = iter_images(source)
    if not image_paths:
        raise SystemExit(f"No images found: {source}")

    for image_path in image_paths:
        result = model.predict(source=str(image_path), conf=args.conf, imgsz=args.imgsz, verbose=False)[0]
        result.save(filename=str(annotated_dir / image_path.name))
        names = result.names
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            rows.append(
                {
                    "image": image_path.name,
                    "label": "",
                    "confidence": "",
                    "x1": "",
                    "y1": "",
                    "x2": "",
                    "y2": "",
                }
            )
            print(f"{image_path.name}: no detections")
            continue

        detections = []
        for box in boxes:
            cls_id = int(box.cls.item())
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = [round(float(value), 2) for value in box.xyxy[0].tolist()]
            label = str(names.get(cls_id, cls_id))
            rows.append(
                {
                    "image": image_path.name,
                    "label": label,
                    "confidence": round(confidence, 4),
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                }
            )
            detections.append(f"{label}:{confidence:.2f}")
        print(f"{image_path.name}: {', '.join(detections)}")

    csv_path = output_dir / "detections.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "label", "confidence", "x1", "y1", "x2", "y2"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"IMAGES={len(image_paths)}")
    print(f"CSV={csv_path}")
    print(f"ANNOTATED={annotated_dir}")


if __name__ == "__main__":
    main()
