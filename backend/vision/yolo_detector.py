from pathlib import Path

import numpy as np

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover - helpful message on edge devices
    YOLO = None

from backend.schemas import Detection


class YoloDetector:
    def __init__(self, model_path: str | Path = "models/yolo11n.pt", conf: float = 0.5):
        if YOLO is None:
            raise RuntimeError("ultralytics is not installed. Run pip install -r requirements.txt")
        self.model_path = str(model_path)
        self.conf = conf
        self.model = YOLO(self.model_path)

    def predict(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(frame, conf=self.conf, verbose=False)
        detections: list[Detection] = []
        if not results:
            return detections

        names = results[0].names
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append(
                Detection(
                    label=names.get(cls_id, str(cls_id)),
                    confidence=float(box.conf[0]),
                    bbox_xyxy=(x1, y1, x2, y2),
                )
            )
        return detections
