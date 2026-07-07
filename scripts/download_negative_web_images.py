"""下载非航拍负样本图片，用于降低无人机/灭火器联合模型误检率。"""

from __future__ import annotations

import argparse
import time
import urllib.request
from pathlib import Path


KEYWORDS = {
    "bird_sky": "bird,sky",
    "airplane_sky": "airplane,sky",
    "helicopter": "helicopter",
    "ceiling_light": "ceiling-light",
    "electric_fan": "electric-fan",
    "indoor_room": "indoor,room",
}


def download(url: str, output: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "DnB26SmartHome/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED {output.name}: {exc}")
        return False

    if len(data) < 10_000 or not data.startswith(b"\xff\xd8"):
        print(f"INVALID {output.name}: {len(data)} bytes")
        return False

    output.write_bytes(data)
    print(f"DOWNLOADED {output.name}: {len(data)} bytes")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Download non-aerial negative images for detector training.")
    parser.add_argument("--output", default="data/sources/web_negative_non_aerial", help="Output directory")
    parser.add_argument("--per-keyword", type=int, default=20, help="Images per keyword group")
    args = parser.parse_args()

    output_root = Path(args.output)
    output_root.mkdir(parents=True, exist_ok=True)
    total = 0
    for group, keyword in KEYWORDS.items():
        group_dir = output_root / group
        group_dir.mkdir(parents=True, exist_ok=True)
        for idx in range(1, args.per_keyword + 1):
            output = group_dir / f"{group}_{idx:03d}.jpg"
            if output.exists():
                continue
            lock = 900_000 + idx + (list(KEYWORDS).index(group) * 10_000)
            url = f"http://loremflickr.com/1200/800/{keyword}?lock={lock}"
            if download(url, output):
                total += 1
            time.sleep(0.7)

    print(f"TOTAL_NEW={total}")
    print(f"OUTPUT={output_root}")


if __name__ == "__main__":
    main()
