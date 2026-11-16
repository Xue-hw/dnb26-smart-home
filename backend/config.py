from pathlib import Path
import os
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class VisionSettings(BaseModel):
    model_path: Path = Path("models/yolo11n.pt")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    image_size: int = Field(default=640, ge=160)
    detections_dir: Path = Path("data/detections")


@dataclass
class Settings:
    """Deployment configuration; all secrets stay in the process environment."""

    database_host: str = '127.0.0.1'
    database_port: int = 3306
    database_user: str = 'dnb26'
    database_password: str = ''
    database_name: str = 'smarthome_db'
    database_init: bool = True
    data_dir: Path = Path('data/runtime')
    custom_model: Path = Path('deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt')
    general_model: Path = Path('models/yolo11n.pt')
    face_predictor: Path = Path('integrations/face_recognition/shape_predictor_68_face_landmarks.dat')
    camera_source: str = '0'
    camera_enabled: bool = True
    camera_width: int = 640
    camera_height: int = 480
    inference_size: int = 640
    inference_interval: float = .15
    confidence: float = .4
    hardware_mode: str = 'mock'
    serial_port: str = '/dev/ttyACM0'
    serial_baud: int = 115200
    gateway_token: str = ''
    api_token: str = ''
    allow_unauthenticated_writes: bool = False
    cors_origins: list[str] = field(default_factory=list)
    face_tolerance: float = .45
    face_enabled: bool = True
    auto_bootstrap_faces: bool = False
    bootstrap_faces_dir: Path = Path('integrations/face_recognition/photos')

    @classmethod
    def from_env(cls):
        values = {}
        defaults = cls()
        for key in cls.__dataclass_fields__:
            raw = os.getenv('DNB_' + key.upper())
            if raw is None:
                continue
            value = getattr(defaults, key)
            if isinstance(value, bool):
                values[key] = raw.lower() in ('true', '1', 'yes', 'on')
            elif isinstance(value, Path):
                values[key] = Path(raw).expanduser().resolve()
            elif isinstance(value, int):
                values[key] = int(raw)
            elif isinstance(value, float):
                values[key] = float(raw)
            elif isinstance(value, list):
                values[key] = [x.strip() for x in raw.split(',') if x.strip()]
            else:
                values[key] = raw
        return cls(**values)
