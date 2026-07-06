from pathlib import Path


def build_output_path(image_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path
    return Path("data/detections") / f"{image_path.stem}_detected{image_path.suffix}"


def parse_class_filter(classes: str | None) -> list[str] | None:
    if classes is None:
        return None
    parsed = [item.strip() for item in classes.split(",") if item.strip()]
    return parsed or None
