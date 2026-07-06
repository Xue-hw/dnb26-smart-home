from pathlib import Path
from pydantic import BaseModel, Field


class VisionSettings(BaseModel):
    model_path: Path = Path("models/yolo11n.pt")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    image_size: int = Field(default=640, ge=160)
    detections_dir: Path = Path("data/detections")
