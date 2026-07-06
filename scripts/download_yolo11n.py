import argparse
from pathlib import Path

from _project_path import add_project_root

add_project_root()

from backend.config import VisionSettings


def main() -> None:
    parser = argparse.ArgumentParser(description="Download/cache YOLO11n weights.")
    parser.add_argument("--output", default=str(VisionSettings().model_path), help="Target weight path")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        print(f"YOLO11n already exists: {output_path}")
        return

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("ultralytics is not installed. Run: pip install -r requirements.txt") from exc

    YOLO("yolo11n.pt")
    downloaded = Path("yolo11n.pt")
    if downloaded.exists():
        downloaded.replace(output_path)
    print(f"YOLO11n ready: {output_path}")


if __name__ == "__main__":
    main()
