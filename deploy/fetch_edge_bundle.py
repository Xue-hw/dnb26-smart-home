"""Download verified Ubuntu ARM64 packages and CPython wheels on the PC.

The board need not have a gateway or DNS. Package filenames and SHA-256 hashes
come from its existing Ubuntu apt index; packages are extracted in a private
application prefix, never installed system-wide.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import gzip
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

PACKAGES = ("mysql-server-core-8.0", "libmecab2", "libprotobuf-lite23", "nginx-light", "libstdc++6")


def apt_packages(host: str) -> list[dict[str, str]]:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, "apt-cache show " + " ".join(PACKAGES)],
        check=True, capture_output=True, text=True,
    )
    selected = {}
    for block in result.stdout.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(" "))
        name = fields.get("Package")
        if name in PACKAGES and name not in selected and "Filename" in fields:
            selected[name] = {k: fields[k] for k in ("Package", "Version", "Filename", "SHA256")}
    if set(selected) != set(PACKAGES):
        raise RuntimeError("Board apt index lacks requested packages")
    return list(selected.values())


def current_packages() -> list[dict[str, str]]:
    selected = {}
    for suite, component in (("jammy", "main"), ("jammy", "universe"), ("jammy-updates", "main"), ("jammy-updates", "universe")):
        url = f"https://ports.ubuntu.com/ubuntu-ports/dists/{suite}/{component}/binary-arm64/Packages.gz"
        with urllib.request.urlopen(url, timeout=120) as response:
            content = gzip.decompress(response.read()).decode()
        for block in content.split("\n\n"):
            fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(" "))
            if fields.get("Package") in PACKAGES:
                selected[fields["Package"]] = {k: fields[k] for k in ("Package", "Version", "Filename", "SHA256")}
    if set(selected) != set(PACKAGES):
        raise RuntimeError(f"Current Ubuntu index lacks requested packages: {set(PACKAGES) - set(selected)}")
    return list(selected.values())


def fetch_package(item: dict[str, str], target: Path) -> None:
    output = target / Path(item["Filename"]).name
    if output.exists() and hashlib.sha256(output.read_bytes()).hexdigest() == item["SHA256"]:
        return
    temporary = output.with_suffix(".part")
    url = "https://ports.ubuntu.com/ubuntu-ports/" + item["Filename"]
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != item["SHA256"]:
        raise RuntimeError(f"Package checksum mismatch: {output.name}")
    temporary.replace(output)
    print("Verified:", output.name, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="orangepi-aipro")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packages-only", action="store_true")
    parser.add_argument("--wheels-only", action="store_true")
    args = parser.parse_args()
    debs, wheels = args.output / "debs", args.output / "wheels"
    debs.mkdir(parents=True, exist_ok=True)
    wheels.mkdir(parents=True, exist_ok=True)
    if not args.wheels_only:
        packages = current_packages()
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda item: fetch_package(item, debs), packages))
        (args.output / "packages.json").write_text(json.dumps(packages, indent=2), encoding="utf-8")
    if not args.packages_only:
        env = os.environ.copy()
        for kind, proxy in urllib.request.getproxies().items():
            if kind in ("http", "https"):
                env[f"{kind.upper()}_PROXY"] = proxy
        subprocess.run([
            sys.executable, "-m", "pip", "download", "--dest", str(wheels),
            "--index-url", "https://pypi.org/simple",
            "--platform", "manylinux2014_aarch64", "--platform", "manylinux_2_28_aarch64",
            "--python-version", "310", "--implementation", "cp", "--abi", "cp310",
            "--only-binary=:all:", "-r", str(Path(__file__).with_name("edge-requirements.txt")),
        ], check=True, env=env)


if __name__ == "__main__":
    main()
