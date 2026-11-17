"""Audit original validation against the candidate training split without changing data."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path: Path) -> tuple[str, int]:
    with Image.open(path) as original:
        image = original.convert("RGB")
        digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
        pixels = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return digest, bits


def intersections(training: dict, validation: dict, threshold: int = 4) -> dict:
    exact_pairs = []
    near_pairs = []
    near_validation = set()
    near_training = set()
    pair_count = 0
    for val_path, (val_sha, val_dhash) in validation.items():
        for train_path, (train_sha, train_dhash) in training.items():
            if train_sha == val_sha:
                exact_pairs.append({"validation": val_path, "training": train_path})
            distance = (val_dhash ^ train_dhash).bit_count()
            if distance <= threshold:
                pair_count += 1
                near_validation.add(val_path)
                near_training.add(train_path)
                if len(near_pairs) < 100:
                    near_pairs.append({"validation": val_path, "training": train_path,
                                       "dhash_distance": distance, "exact_pixels": train_sha == val_sha})
    return {"training_images": len(training), "validation_images": len(validation),
            "exact_pixel_pair_count": len(exact_pairs), "exact_pixel_pairs": exact_pairs,
            "dhash_threshold": threshold, "dhash_pair_count": pair_count,
            "validation_images_with_dhash_neighbor": len(near_validation),
            "training_images_with_dhash_neighbor": len(near_training),
            "dhash_pair_examples_first_100": near_pairs}


def scan(folder: Path, workers: int) -> dict:
    paths = sorted(path for path in folder.iterdir()
                   if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    with ThreadPoolExecutor(max_workers=workers) as executor:
        values = list(executor.map(fingerprint, paths))
    return {str(path): value for path, value in zip(paths, values)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "deploy_export/weights/dnb26_drone_fire_bulb_dataset_audit.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite existing audit: {args.output}")
    original = ROOT / "data/datasets/drone_fire_extinguisher"
    candidate = ROOT / "data/datasets/drone_fire_bulb_v2"
    print("Scanning original validation", flush=True)
    validation = scan(original / "images/val", args.workers)
    print("Scanning candidate training", flush=True)
    training = scan(candidate / "images/train", args.workers)
    print("Scanning original training", flush=True)
    original_training = scan(original / "images/train", args.workers)
    bulb_test = scan(candidate / "images/test", args.workers)
    bulb_validation = {path: values for path, values in scan(candidate / "images/val", args.workers).items()
                       if Path(path).name.startswith("oi_bulb_")}
    result = {
        "method": "Decoded RGB SHA256 including dimensions; 64-bit grayscale dHash at 9x8, distance <=4",
        "candidate_training_vs_original_validation": intersections(training, validation),
        "original_training_vs_original_validation": intersections(original_training, validation),
        "candidate_training_vs_bulb_holdout": intersections(training, bulb_test),
        "candidate_training_vs_bulb_validation": intersections(training, bulb_validation),
        "limitations": [
            "A dHash neighbor is a visual similarity flag, not proof of source identity or leakage",
            "No scene-ID or video-sequence grouping is available for every old-class image",
            "Candidate starts from old weights; removing training duplicates does not undo prior weight exposure",
            "The same old validation split supports a paired comparison, not an independent old-class holdout",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: {k: v for k, v in value.items() if not isinstance(v, list)}
                      for key, value in result.items() if isinstance(value, dict)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
