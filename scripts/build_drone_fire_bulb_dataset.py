"""Build a traceable three-class dataset from existing labels and Open Images.

Downloads only a bounded prefix of Google's official, image-ID-sorted box CSV.
The selected images retain manually annotated Light bulb boxes; this script
never generates pseudo boxes. Exact decoded duplicates are excluded across
all splits. New images are content-hash split with a fixed seed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BULB_ID = "/m/0h8l4fh"
ANNOTATIONS_URL = "https://storage.googleapis.com/openimages/2018_04/train/train-annotations-bbox.csv"
HEADER = "ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside"
SPLITS = ("train", "val", "test")


def box_to_yolo(row: dict[str, str]) -> str:
    xmin, xmax, ymin, ymax = (float(row[k]) for k in ("XMin", "XMax", "YMin", "YMax"))
    if not all(math.isfinite(v) for v in (xmin, xmax, ymin, ymax)):
        raise ValueError("Non-finite Open Images box")
    if not (0 <= xmin < xmax <= 1 and 0 <= ymin < ymax <= 1):
        raise ValueError(f"Invalid Open Images box: {row}")
    return f"2 {(xmin+xmax)/2:.6f} {(ymin+ymax)/2:.6f} {xmax-xmin:.6f} {ymax-ymin:.6f}"


def validate_label(line: str) -> None:
    parts = line.split()
    if len(parts) != 5 or parts[0] not in {"0", "1", "2"}:
        raise ValueError(f"Invalid YOLO class/columns: {line}")
    cx, cy, w, h = map(float, parts[1:])
    if not all(math.isfinite(v) for v in (cx, cy, w, h)):
        raise ValueError(f"Non-finite YOLO coordinate: {line}")
    if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError(f"Invalid YOLO geometry: {line}")


def canonical_fingerprint(path: Path) -> str:
    with Image.open(path) as image:
        image = image.convert("RGB")
        payload = str(image.size).encode() + image.tobytes()
    return hashlib.sha256(payload).hexdigest()


def link_or_copy(source: Path, destination: Path) -> None:
    """Reuse immutable source bytes without duplicating a local training corpus."""
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def classify_split(fingerprint: str) -> str:
    bucket = int(hashlib.sha256(("dnb26-bulb-v1:" + fingerprint).encode()).hexdigest()[:12], 16) % 100
    return "train" if bucket < 75 else "val" if bucket < 90 else "test"


def assign_bulb_split(path: Path, fingerprint: str, groups: list[tuple[int, str]]) -> str:
    """Keep perceptually close bulb images together, without changing labels."""
    with Image.open(path) as image:
        pixels = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).tobytes()
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    for prior, split in groups:
        if (prior ^ bits).bit_count() <= 4:
            return split
    split = classify_split(fingerprint)
    groups.append((bits, split))
    return split


def get_bytes(url: str, *, start: int | None = None, size: int | None = None) -> bytes:
    headers = {"User-Agent": "DnB26-academic-dataset-builder/1.0"}
    if start is not None and size is not None:
        headers["Range"] = f"bytes={start}-{start + size - 1}"
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers=headers), timeout=90) as response:
                if start is not None and response.status != 206:
                    raise RuntimeError("Annotation server did not honor bounded range request")
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def fetch_annotations(source_dir: Path, sample_mb: int, workers: int) -> dict[str, list[dict[str, str]]]:
    """Fetch consecutive 8MiB blocks with overlaps, preserving complete records."""
    cache = source_dir / f"light_bulb_boxes_prefix_{sample_mb}mb.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    known_prefix_mb = 0
    for previous in source_dir.glob("light_bulb_boxes_prefix_*mb.json"):
        previous_mb = int(previous.stem.removeprefix("light_bulb_boxes_prefix_").removesuffix("mb"))
        if known_prefix_mb < previous_mb < sample_mb and previous_mb % 8 == 0:
            groups = defaultdict(list, json.loads(previous.read_text(encoding="utf-8")))
            known_prefix_mb = previous_mb
    chunk_size = 8 * 1024 * 1024
    blocks = list(range(known_prefix_mb // 8, math.ceil(sample_mb * 1024 * 1024 / chunk_size)))

    def chunk(index: int):
        offset = index * chunk_size
        # Overlap ensures boundary images are not partially annotated.
        start = max(0, offset - 65536)
        content = get_bytes(ANNOTATIONS_URL, start=start, size=chunk_size + 131072)
        lines = content.decode("utf-8").splitlines()
        if start:
            lines = lines[1:]
        lines = lines[:-1]
        rows = []
        for raw in lines:
            if f",{BULB_ID}," in raw:
                row = dict(zip(HEADER.split(","), next(csv.reader([raw]))))
                if row.get("IsGroupOf") == "0" and row.get("IsDepiction") == "0":
                    box_to_yolo(row)
                    rows.append(row)
        return index, rows

    seen_rows: set[str] = {json.dumps(row, sort_keys=True) for rows in groups.values() for row in rows}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(chunk, i) for i in blocks]
        for future in as_completed(futures):
            index, rows = future.result()
            for row in rows:
                key = json.dumps(row, sort_keys=True)
                if key not in seen_rows:
                    groups[row["ImageID"]].append(row)
                    seen_rows.add(key)
            print(f"annotations block {index+1}/{math.ceil(sample_mb/8)}, bulb images={len(groups)}", flush=True)
    cache.write_text(json.dumps(groups, ensure_ascii=False), encoding="utf-8")
    return dict(groups)


def download_images(source_dir: Path, annotations: dict[str, list], limit: int, workers: int) -> list[Path]:
    image_dir = source_dir / "images"
    image_dir.mkdir(exist_ok=True)
    ids = sorted(annotations, key=lambda x: hashlib.sha256(("26:" + x).encode()).hexdigest())[:limit]

    def download(image_id: str):
        target = image_dir / f"{image_id}.jpg"
        if not target.exists():
            data = get_bytes(f"https://open-images-dataset.s3.amazonaws.com/train/{image_id}.jpg")
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            target.write_bytes(data)
        return target

    paths = []
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(download, image_id): image_id for image_id in ids}
        for future in as_completed(future_map):
            try:
                paths.append(future.result())
            except Exception as error:
                failures.append({"image_id": future_map[future], "error": str(error)})
            if (len(paths) + len(failures)) % 25 == 0:
                print(f"images {len(paths)}/{len(ids)} downloaded, failed={len(failures)}", flush=True)
    (source_dir / "download_failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(paths) < 30:
        raise RuntimeError(f"Too few successfully downloaded bulb images: {len(paths)}")
    return sorted(paths)


def build(existing: Path, output: Path, source: Path, sample_mb: int, limit: int, workers: int) -> dict:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing dataset: {output}")
    source.mkdir(parents=True, exist_ok=True)
    annotations = fetch_annotations(source, sample_mb, workers)
    bulb_paths = download_images(source, annotations, limit, workers)
    print(f"Copying existing dataset, then adding {len(bulb_paths)} bulb images", flush=True)
    for split in SPLITS:
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)
    fingerprints: dict[str, str] = {}
    records = []
    dropped = []
    # Reserve existing validation before train so duplicates cannot leak into training.
    for split in ("val", "train"):
        for image in sorted((existing / "images" / split).iterdir()):
            if image.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            label = existing / "labels" / split / f"{image.stem}.txt"
            text = label.read_text(encoding="utf-8").strip()
            for line in text.splitlines():
                validate_label(line)
            fingerprint = canonical_fingerprint(image)
            if fingerprint in fingerprints:
                dropped.append({"path": str(image), "duplicate_of": fingerprints[fingerprint]})
                continue
            fingerprints[fingerprint] = str(image)
            name = image.name
            link_or_copy(image, output / "images" / split / name)
            (output / "labels" / split / f"{image.stem}.txt").write_text(text + "\n" if text else "", encoding="utf-8")
            records.append({"source": "existing_drone_fire", "image": name, "split": split, "sha256_pixels": fingerprint})
    bulb_groups: list[tuple[int, str]] = []
    for image in bulb_paths:
        fingerprint = canonical_fingerprint(image)
        if fingerprint in fingerprints:
            dropped.append({"path": str(image), "duplicate_of": fingerprints[fingerprint]})
            continue
        fingerprints[fingerprint] = str(image)
        split = assign_bulb_split(image, fingerprint, bulb_groups)
        name = f"oi_bulb_{image.name}"
        link_or_copy(image, output / "images" / split / name)
        lines = [box_to_yolo(row) for row in annotations[image.stem]]
        (output / "labels" / split / f"oi_bulb_{image.stem}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        records.append({"source": "open_images_v4_train", "image": name, "image_id": image.stem, "split": split,
                        "sha256_pixels": fingerprint, "boxes": len(lines),
                        "url": f"https://open-images-dataset.s3.amazonaws.com/train/{image.stem}.jpg"})
    counts = Counter((r["source"], r["split"]) for r in records)
    metadata = {"seed": "dnb26-bulb-v1", "names": {0: "drone", 1: "fire_extinguisher", 2: "light_bulb"},
                "annotation_url": ANNOTATIONS_URL, "annotation_prefix_mb": sample_mb,
                "class_id": BULB_ID, "annotations_license": "CC BY 4.0",
                "images_license": "Open Images lists CC BY 2.0; original per-image rights must be checked before redistribution",
                "source_license_url": "https://storage.googleapis.com/openimages/web/factsfigures_v7.html",
                "counts": {f"{s}/{p}": n for (s, p), n in sorted(counts.items())},
                "duplicates_removed": dropped, "images": records,
                "near_duplicate_split_grouping": "64-bit dHash distance <= 4 stays in the representative split",
                "limitations": ["Open Images bulb images sampled from a bounded ID-sorted annotation prefix",
                                "Exact decoded-pixel deduplication does not exclude every near-duplicate scene",
                                "Bulb-only test split is held out; old classes retain their existing validation split",
                                "Other target classes potentially visible in OI bulb images have not been manually exhaustively relabeled"]}
    (output / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "data.yaml").write_text(f"path: {output.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: drone\n  1: fire_extinguisher\n  2: light_bulb\n", encoding="utf-8")
    print(json.dumps(metadata["counts"], indent=2), flush=True)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, default=ROOT / "data/datasets/drone_fire_extinguisher")
    parser.add_argument("--output", type=Path, default=ROOT / "data/datasets/drone_fire_bulb_v1")
    parser.add_argument("--source", type=Path, default=ROOT / "data/sources/open_images_light_bulb")
    parser.add_argument("--sample-mb", type=int, default=256)
    parser.add_argument("--bulb-limit", type=int, default=600)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    build(args.existing, args.output, args.source, args.sample_mb, args.bulb_limit, args.workers)


if __name__ == "__main__":
    main()
