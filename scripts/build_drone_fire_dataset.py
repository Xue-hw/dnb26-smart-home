"""构建无人机和灭火器两类 YOLO 数据集。

本脚本把 Hugging Face 无人机 COCO/parquet 数据和 FF-dataset 消防设施
YOLO 数据合并为项目统一格式，并将类别重映射为 drone 与 fire_extinguisher。
也可以把额外负样本图片加入训练集，对应标签文件为空，用于抑制误检。
"""

import argparse
import random
import shutil
import zipfile
from pathlib import Path

import polars as pl

from _project_path import add_project_root

add_project_root()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRONE_SOURCE = PROJECT_ROOT / "data" / "sources" / "hf-drone-detection-dataset" / "data"
FIRE_SOURCE_ZIP = PROJECT_ROOT / "data" / "sources" / "FF-dataset.zip"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "datasets" / "drone_fire_extinguisher"


def write_yaml(output_dir: Path) -> None:
    (output_dir / "data.yaml").write_text(
        "\n".join(
            [
                f"path: {output_dir.as_posix()}",
                "train: images/train",
                "val: images/val",
                "names:",
                "  0: drone",
                "  1: fire_extinguisher",
                "",
            ]
        ),
        encoding="utf-8",
    )


def yolo_line(class_id: int, bbox: list[float], width: int, height: int) -> str:
    x, y, box_w, box_h = bbox
    cx = (x + box_w / 2) / width
    cy = (y + box_h / 2) / height
    return f"{class_id} {cx:.6f} {cy:.6f} {box_w / width:.6f} {box_h / height:.6f}"


def ensure_split_dirs(output_dir: Path) -> None:
    for split in ("train", "val"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)


def iter_drone_rows(files: list[Path]):
    for file_path in files:
        for row in pl.read_parquet(file_path).iter_rows(named=True):
            yield row


def convert_drone_split(source_files: list[Path], output_dir: Path, split: str, limit: int, seed: int) -> int:
    rows = list(iter_drone_rows(source_files))
    random.Random(seed).shuffle(rows)
    selected = rows[:limit]

    image_dir = output_dir / "images" / split
    label_dir = output_dir / "labels" / split
    for idx, row in enumerate(selected):
        image_name = f"drone_{split}_{idx:06d}.jpg"
        image_bytes = row["image"]["bytes"]
        width = int(row["width"])
        height = int(row["height"])
        objects = row["objects"]
        lines = [yolo_line(0, bbox, width, height) for bbox in objects["bbox"]]

        (image_dir / image_name).write_bytes(image_bytes)
        (label_dir / image_name.replace(".jpg", ".txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return len(selected)


def zip_names(zip_path: Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as archive:
        return archive.namelist()


def convert_fire_split(
    zip_path: Path,
    output_dir: Path,
    source_split: str,
    target_split: str,
    limit: int | None = None,
) -> tuple[int, int]:
    image_prefix = f"FF-dataset/images/{source_split}/"
    label_prefix = f"FF-dataset/labels/{source_split}/"
    images_written = 0
    boxes_written = 0

    with zipfile.ZipFile(zip_path) as archive:
        image_names = [
            name
            for name in archive.namelist()
            if name.startswith(image_prefix)
            and not name.startswith("__MACOSX/")
            and Path(name).suffix.lower() in {".jpg", ".jpeg", ".png"}
            and "/._" not in name
        ]

        for source_image in image_names[:limit]:
            stem = Path(source_image).stem
            source_label = f"{label_prefix}{stem}.txt"
            output_image = output_dir / "images" / target_split / f"fire_{target_split}_{stem}{Path(source_image).suffix.lower()}"
            output_label = output_dir / "labels" / target_split / f"fire_{target_split}_{stem}.txt"

            lines: list[str] = []
            try:
                label_text = archive.read(source_label).decode("utf-8")
            except KeyError:
                label_text = ""
            for raw_line in label_text.splitlines():
                parts = raw_line.split()
                if len(parts) != 5:
                    continue
                if parts[0] == "5":
                    lines.append("1 " + " ".join(parts[1:]))

            output_image.write_bytes(archive.read(source_image))
            output_label.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
            images_written += 1
            boxes_written += len(lines)

    return images_written, boxes_written


def copy_negative_train_images(source_dir: Path, output_dir: Path, limit: int | None = None) -> int:
    if not source_dir.exists():
        return 0

    image_paths = [
        path
        for path in sorted(source_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    if limit is not None:
        image_paths = image_paths[:limit]

    image_dir = output_dir / "images" / "train"
    label_dir = output_dir / "labels" / "train"
    for idx, source_image in enumerate(image_paths):
        suffix = source_image.suffix.lower()
        image_name = f"negative_train_{idx:06d}{suffix}"
        shutil.copy2(source_image, image_dir / image_name)
        (label_dir / f"negative_train_{idx:06d}.txt").write_text("", encoding="utf-8")

    return len(image_paths)


def build_dataset(args: argparse.Namespace) -> None:
    output_dir = Path(args.output)
    if output_dir.exists() and args.force:
        shutil.rmtree(output_dir)
    ensure_split_dirs(output_dir)

    train_files = sorted(DRONE_SOURCE.glob("train-*.parquet"))
    test_files = sorted(DRONE_SOURCE.glob("test-*.parquet"))
    if not train_files or not test_files:
        raise SystemExit(f"Drone parquet files not found under {DRONE_SOURCE}")
    if not FIRE_SOURCE_ZIP.exists():
        raise SystemExit(f"Fire dataset zip not found: {FIRE_SOURCE_ZIP}")

    drone_train = convert_drone_split(train_files, output_dir, "train", args.drone_train, args.seed)
    drone_val = convert_drone_split(test_files, output_dir, "val", args.drone_val, args.seed + 1)
    fire_train_limit = args.fire_train or None
    fire_val_limit = args.fire_val or None
    fire_train_images, fire_train_boxes = convert_fire_split(
        FIRE_SOURCE_ZIP, output_dir, "train", "train", fire_train_limit
    )
    fire_val_images, fire_val_boxes = convert_fire_split(FIRE_SOURCE_ZIP, output_dir, "test", "val", fire_val_limit)
    negative_images = copy_negative_train_images(
        Path(args.negative_dir), output_dir, args.negative_limit or None
    ) if args.negative_dir else 0
    write_yaml(output_dir)

    print(f"Dataset ready: {output_dir}")
    print(f"drone train images: {drone_train}")
    print(f"drone val images: {drone_val}")
    print(f"fire train images: {fire_train_images}, fire extinguisher boxes: {fire_train_boxes}")
    print(f"fire val images: {fire_val_images}, fire extinguisher boxes: {fire_val_boxes}")
    print(f"negative train images: {negative_images}")
    print(f"config: {output_dir / 'data.yaml'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the DnB26 drone/fire-extinguisher YOLO dataset.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output YOLO dataset directory.")
    parser.add_argument("--drone-train", type=int, default=3000, help="Number of drone train images to sample.")
    parser.add_argument("--drone-val", type=int, default=500, help="Number of drone validation images to sample.")
    parser.add_argument("--fire-train", type=int, default=0, help="Number of fire train images to use. 0 means all.")
    parser.add_argument("--fire-val", type=int, default=0, help="Number of fire validation images to use. 0 means all.")
    parser.add_argument("--negative-dir", help="Directory of negative/background images to add to train split.")
    parser.add_argument("--negative-limit", type=int, default=0, help="Number of negative images to add. 0 means all.")
    parser.add_argument("--seed", type=int, default=26, help="Sampling seed.")
    parser.add_argument("--force", action="store_true", help="Delete and rebuild the output dataset directory.")
    args = parser.parse_args()
    build_dataset(args)


if __name__ == "__main__":
    main()
