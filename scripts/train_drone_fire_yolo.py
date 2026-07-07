"""训练无人机和灭火器两类 YOLO11n 模型。

默认读取项目内合并后的 data.yaml，并使用 models/yolo11n.pt 作为预训练权重。
正式训练前可用 --fraction 搭配 --epochs 1 做 CUDA 和训练流程冒烟测试。
"""

import argparse
from pathlib import Path

from _project_path import add_project_root

add_project_root()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = PROJECT_ROOT / "data" / "datasets" / "drone_fire_extinguisher" / "data.yaml"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "yolo11n.pt"
DEFAULT_PROJECT = PROJECT_ROOT / "runs" / "detect"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLO11n on drone and fire-extinguisher classes.")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="YOLO data.yaml path.")
    parser.add_argument("--model", default=str(DEFAULT_MODEL), help="Initial YOLO weights.")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", default="16", help="Batch size or 'auto'.")
    parser.add_argument("--device", default="0", help="Use '0' for first CUDA GPU, or 'cpu'.")
    parser.add_argument("--name", default="dnb26_drone_fire_yolo11n")
    parser.add_argument("--fraction", type=float, default=1.0, help="Dataset fraction used for training.")
    parser.add_argument("--workers", type=int, default=8, help="Number of dataloader workers.")
    parser.add_argument("--optimizer", default="auto", help="Optimizer name, for example auto, AdamW, SGD.")
    parser.add_argument("--lr0", type=float, help="Initial learning rate. Leave unset to use Ultralytics default.")
    parser.add_argument("--lrf", type=float, help="Final learning rate factor. Leave unset to use Ultralytics default.")
    args = parser.parse_args()

    data_path = Path(args.data)
    model_path = Path(args.model)
    if not data_path.exists():
        raise SystemExit(f"Dataset config not found: {data_path}")
    if not model_path.exists():
        raise SystemExit(f"Model weights not found: {model_path}")

    try:
        import torch
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit("Missing training dependencies. Run: pip install -r requirements.txt") from exc

    if args.device != "cpu" and not torch.cuda.is_available():
        raise SystemExit(
            "CUDA is not available in this Python environment. Install CUDA-enabled PyTorch or use --device cpu."
        )

    batch: int | str = "auto" if args.batch == "auto" else int(args.batch)
    model = YOLO(str(model_path))
    train_kwargs = {
        "data": str(data_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": batch,
        "device": args.device,
        "fraction": args.fraction,
        "workers": args.workers,
        "project": str(DEFAULT_PROJECT),
        "name": args.name,
        "optimizer": args.optimizer,
    }
    if args.lr0 is not None:
        train_kwargs["lr0"] = args.lr0
    if args.lrf is not None:
        train_kwargs["lrf"] = args.lrf

    results = model.train(**train_kwargs)
    print(results)


if __name__ == "__main__":
    main()
