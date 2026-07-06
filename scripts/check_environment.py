import argparse
import importlib.util
import platform
from pathlib import Path

from _project_path import add_project_root

add_project_root()

from backend.config import VisionSettings


def package_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the smart-home vision environment.")
    parser.add_argument("--model", default=str(VisionSettings().model_path), help="YOLO model path")
    args = parser.parse_args()

    model_path = Path(args.model)
    checks = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ultralytics": "ok" if package_available("ultralytics") else "missing",
        "opencv": "ok" if package_available("cv2") else "missing",
        "numpy": "ok" if package_available("numpy") else "missing",
        "model": "found" if model_path.exists() else f"missing ({model_path})",
    }

    for name, value in checks.items():
        print(f"{name}: {value}")


if __name__ == "__main__":
    main()
