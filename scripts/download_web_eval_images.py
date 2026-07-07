"""从 Wikimedia Commons 下载公开测试图片，用于验证联合目标检测模型效果。"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "DnB26SmartHome/0.1 (student evaluation; local testing)"


def api_get(params: dict[str, object]) -> dict[str, object]:
    query = dict(params)
    query["format"] = "json"
    url = API_URL + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def safe_name(text: str) -> str:
    text = re.sub(r"^File:", "", text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return text[:90] or "image"


def collect_items(search_terms: list[str], limit: int) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for term in search_terms:
        data = api_get(
            {
                "action": "query",
                "generator": "search",
                "gsrnamespace": 6,
                "gsrsearch": term,
                "gsrlimit": 30,
                "prop": "imageinfo",
                "iiprop": "url|mime|size",
                "iiurlwidth": 1400,
            }
        )
        pages = data.get("query", {}).get("pages", {})
        if not isinstance(pages, dict):
            continue
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            title = str(page.get("title", ""))
            image_info = page.get("imageinfo") or [{}]
            if not isinstance(image_info, list) or not image_info:
                continue
            info = image_info[0]
            if not isinstance(info, dict):
                continue
            url = info.get("thumburl") or info.get("url")
            mime = str(info.get("mime", ""))
            width = int(info.get("width") or 0)
            height = int(info.get("height") or 0)
            if not url or title in seen:
                continue
            if mime not in {"image/jpeg", "image/png"}:
                continue
            if width < 250 or height < 250:
                continue
            seen.add(title)
            items.append(
                {
                    "title": title,
                    "url": str(url),
                    "mime": mime,
                    "width": width,
                    "height": height,
                    "search_term": term,
                }
            )
            if len(items) >= limit:
                return items
        time.sleep(0.5)
    return items


def download_file(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Download web images for DnB26 detector evaluation.")
    parser.add_argument("--output", default="data/evaluation/web_images", help="Output directory")
    parser.add_argument("--per-class", type=int, default=12, help="Images to download for each class")
    args = parser.parse_args()

    output_dir = Path(args.output)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    search_sets = {
        "drone": [
            "quadcopter drone photograph",
            "DJI drone in flight",
            "unmanned aerial vehicle photograph",
            "multirotor drone outdoor",
            "drone aircraft photo",
        ],
        "fire_extinguisher": [
            "fire extinguisher photograph",
            "portable fire extinguisher",
            "red fire extinguisher wall",
            "fire extinguisher indoor photo",
            "fire safety extinguisher photograph",
        ],
    }

    manifest: list[dict[str, object]] = []
    for label, terms in search_sets.items():
        target_dir = raw_dir / label
        target_dir.mkdir(parents=True, exist_ok=True)
        existing = {path.name for path in target_dir.glob("*") if path.is_file()}
        downloaded = 0
        for index, item in enumerate(collect_items(terms, args.per_class * 3), 1):
            if downloaded >= args.per_class:
                break
            ext = ".jpg" if item["mime"] == "image/jpeg" else ".png"
            filename = f"{label}_{index:02d}_{safe_name(str(item['title']))}"
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                filename += ext
            if filename in existing:
                continue
            path = target_dir / filename
            try:
                download_file(str(item["url"]), path)
            except Exception as exc:  # noqa: BLE001
                print(f"FAILED {label}: {item['title']} - {exc}")
                continue
            downloaded += 1
            manifest.append({**item, "label_query": label, "local_path": str(path)})
            print(f"DOWNLOADED {label}: {path.name}")
            time.sleep(0.5)

    manifest_path = output_dir / "manifest.json"
    previous: list[dict[str, object]] = []
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(previous + manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"TOTAL_NEW={len(manifest)}")
    print(f"TOTAL_FILES={sum(1 for _ in raw_dir.rglob('*') if _.is_file())}")
    print(f"MANIFEST={manifest_path}")


if __name__ == "__main__":
    main()
