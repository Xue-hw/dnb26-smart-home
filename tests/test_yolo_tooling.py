from pathlib import Path

from backend.config import VisionSettings
from backend.vision.cli_utils import build_output_path, parse_class_filter


def test_vision_settings_default_to_yolo11n() -> None:
    settings = VisionSettings()
    assert settings.model_path == Path("models/yolo11n.pt")
    assert settings.image_size == 640
    assert settings.confidence == 0.5


def test_build_output_path_uses_detection_directory() -> None:
    output = build_output_path(Path("samples/front-door.jpg"), None)
    assert output == Path("data/detections/front-door_detected.jpg")


def test_build_output_path_respects_explicit_output() -> None:
    output = build_output_path(Path("samples/front-door.jpg"), Path("out/result.jpg"))
    assert output == Path("out/result.jpg")


def test_parse_class_filter_removes_empty_items() -> None:
    assert parse_class_filter("person, car,,bottle ") == ["person", "car", "bottle"]
    assert parse_class_filter(None) is None
