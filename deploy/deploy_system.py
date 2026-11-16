"""Build a bounded release archive and transfer it over an existing SSH alias.

The release excludes credentials, training data, caches and Git history. Mutable
MySQL data and models remain in shared/, outside the versioned current symlink.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import shlex
import subprocess
import tarfile


def included(path: Path) -> bool:
    return (not any(part in {"__pycache__", "node_modules", ".git", ".gradle", ".venv"} for part in path.parts)
            and path.parts[:2] != ("deploy", "local")
            and path.suffix not in {".pyc", ".key", ".pem"}
            and path.name not in {"credentials.json", "app.env"}
            and not path.name.startswith(".env"))


def build_archive(repo: Path, output: Path) -> list[str]:
    allowed = [repo / "backend", repo / "deploy", repo / "integrations/database",
               repo / "integrations/face_recognition/photos", repo / "integrations/gui/project/dist"]
    if not (allowed[-1] / "index.html").is_file():
        raise FileNotFoundError("Build the real HTTP GUI before packaging a release")
    names = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for folder in allowed:
            for item in sorted(folder.rglob("*")):
                relative = item.relative_to(repo)
                if item.is_file() and not item.is_symlink() and included(relative):
                    archive.add(item, arcname=relative.as_posix(), recursive=False)
                    names.append(relative.as_posix())
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="orangepi-aipro")
    parser.add_argument("--remote-root", default="/home/HwHiAiUser/projects/dnb26-smart-home")
    parser.add_argument("--release", default=datetime.now(timezone.utc).strftime("release-%Y%m%d-%H%M%S"))
    parser.add_argument("--output", type=Path, default=Path("D:/CodexData/scratch/dnb26-system-deploy/release.tar.gz"))
    parser.add_argument("--activate", action="store_true", help="Switch current and restart an already-bootstrapped API/Web")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.release) or args.release in (".", ".."):
        raise ValueError("Invalid release name")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.remote_root) or ".." in args.remote_root.split("/") or args.remote_root == "/":
        raise ValueError("Expected isolated absolute remote project root")
    repo = Path(__file__).resolve().parents[1]
    names = build_archive(repo, args.output)
    remote = args.remote_root
    destination = f"{remote}/releases/{args.release}"
    subprocess.run(["ssh", "-o", "BatchMode=yes", args.host,
                    f"mkdir -p {shlex.quote(remote+'/releases')} && mkdir {shlex.quote(destination)}"], check=True)
    subprocess.run(["scp", "-o", "BatchMode=yes", str(args.output), f"{args.host}:{remote}/release.tar.gz"], check=True)
    script = f"set -eu\ntar --warning=no-timestamp -xzf {shlex.quote(remote+'/release.tar.gz')} -C {shlex.quote(destination)}\n"
    script += f"test -f {shlex.quote(destination+'/backend/app.py')}\n"
    if not args.activate:
        # A staged release must not switch the GUI while the old API is running.
        # The first installation needs a current path for bootstrap_edge.py.
        script += f"if [ ! -e {shlex.quote(remote+'/current')} ]; then\n"
    script += f"ln -sfn {shlex.quote(destination)} {shlex.quote(remote+'/current.next')}\n"
    script += f"mv -Tf {shlex.quote(remote+'/current.next')} {shlex.quote(remote+'/current')}\n"
    if not args.activate:
        script += "fi\n"
    if args.activate:
        script += "systemctl --user restart dnb26-api dnb26-web\n"
    # Bytes preserve LF on Windows; text-mode stdin would turn bash input into CRLF.
    subprocess.run(["ssh", "-o", "BatchMode=yes", args.host, "bash", "-s"], input=script.encode("utf-8"), check=True)
    print(f"Transferred {len(names)} files to {destination}")


if __name__ == "__main__":
    main()
