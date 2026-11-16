"""Train, evaluate, and export the three-class DnB26 YOLO11n extension.

Run in the isolated CUDA training environment; existing production weights
are evaluated as a baseline and never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {0: "drone", 1: "fire_extinguisher", 2: "light_bulb"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metrics_summary(metrics) -> dict:
    box = metrics.box
    indices = list(map(int, box.ap_class_index))
    return {
        "overall": {str(k): float(v) for k, v in metrics.results_dict.items()},
        "per_class": {
            str(index): {"name": metrics.names[index], "precision": float(box.p[position]),
                         "recall": float(box.r[position]), "mAP50": float(box.ap50[position]),
                         "mAP50_95": float(box.ap[position])}
            for position, index in enumerate(indices)
        },
        "speed_ms": {str(k): float(v) for k, v in metrics.speed.items()},
    }


def training_summary(results_path: Path) -> dict:
    """Report completed epochs from the durable CSV, including resumed runs."""
    with results_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [{key.strip(): value.strip() for key, value in row.items()}
                for row in csv.DictReader(handle)]
    if not rows:
        raise ValueError("Training result CSV contains no completed epochs")
    best = max(rows, key=lambda row: float(row["metrics/mAP50-95(B)"]))
    return {
        "completed_epochs": len(rows),
        "last_epoch": int(float(rows[-1]["epoch"])),
        "best_epoch_by_validation_map50_95": int(float(best["epoch"])),
        "best_validation_map50_95": float(best["metrics/mAP50-95(B)"]),
        "results_csv": str(results_path),
    }


def baseline_comparison(baseline: dict, candidate: dict) -> dict:
    """Compare semantic class IDs only when both runs evaluated the same split."""
    compared = {}
    for index, original in baseline["per_class"].items():
        current = candidate["per_class"].get(index)
        if current is None or current["name"] != original["name"]:
            raise ValueError(f"Missing or mismatched candidate class: {index}")
        compared[index] = {"name": original["name"], **{
            metric: {"baseline": original[metric], "candidate": current[metric],
                     "delta": current[metric] - original[metric]}
            for metric in ("precision", "recall", "mAP50", "mAP50_95")
        }}
    return {"split": "original_drone_fire_extinguisher_validation", "per_class": compared}


def finalize_training_report(report_path: Path, *, imgsz: int, batch: int,
                             device: str, workers: int, run_name: str) -> dict:
    """Recoverable final audit for a finished run; never change model weights."""
    from ultralytics import YOLO

    report = json.loads(report_path.read_text(encoding="utf-8"))
    checkpoint = Path(report["checkpoint"]["path"])
    if sha256(checkpoint) != report["checkpoint"]["sha256"]:
        raise ValueError("Published checkpoint hash differs from the experiment report")
    report["training"] = training_summary(ROOT / "runs/detect" / run_name / "results.csv")
    audit_path = report_path.with_name("dnb26_drone_fire_bulb_dataset_audit.json")
    if audit_path.is_file():
        report["dataset_overlap_audit"] = {"path": str(audit_path), "sha256": sha256(audit_path),
                                         "results": json.loads(audit_path.read_text(encoding="utf-8"))}
    if "candidate_original_validation" not in report:
        candidate = YOLO(str(checkpoint))
        report["candidate_original_validation"] = metrics_summary(candidate.val(
            data=str(ROOT / "data/datasets/drone_fire_extinguisher/data.yaml"),
            imgsz=imgsz, batch=batch, device=device, workers=workers,
            project=str(ROOT / "runs/detect"), name=run_name + "_original_validation", plots=False,
        ))
    if "baseline_old_classes" in report:
        report["same_split_comparison"] = baseline_comparison(
            report["baseline_old_classes"], report["candidate_original_validation"])
    if "onnx" in report and "input_name" not in report.get("onnx_validation", {}):
        report["onnx_validation"] = verify_onnx(checkpoint, Path(report["onnx"]["path"]))
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def verify_onnx(checkpoint: Path, exported: Path) -> dict:
    """Check graph structure and numerical parity on a deterministic input."""
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    graph = onnx.load(str(exported))
    onnx.checker.check_model(graph)
    session = ort.InferenceSession(str(exported), providers=["CPUExecutionProvider"])
    input_spec = session.get_inputs()[0]
    shape = input_spec.shape
    if not all(isinstance(n, int) and n > 0 for n in shape):
        raise ValueError(f"Expected static export input shape, got {shape}")
    if input_spec.name != "images" or input_spec.type != "tensor(float)" or shape[0] != 1 or shape[1] != 3:
        raise ValueError(f"Unexpected deployment input contract: {input_spec.name} {shape}")
    image = np.random.default_rng(26).random(shape, dtype=np.float32)
    model = YOLO(str(checkpoint)).model.float().cpu().eval()
    torch.set_num_threads(2)
    with torch.inference_mode():
        expected = model(torch.from_numpy(image))[0].numpy()
    actual = session.run(None, {input_spec.name: image})[0]
    expected_boxes = sum((shape[2] // stride) * (shape[3] // stride) for stride in (8, 16, 32))
    if actual.dtype != np.float32 or list(actual.shape) != [1, len(NAMES) + 4, expected_boxes]:
        raise ValueError(f"Unexpected deployment output shape: {actual.shape}")
    np.testing.assert_allclose(actual, expected, rtol=1e-3, atol=1e-3)
    return {"graph_valid": True, "input_name": input_spec.name, "input_dtype": input_spec.type,
            "input_shape": shape, "output_shape": list(actual.shape), "output_dtype": str(actual.dtype),
            "max_abs_error": float(np.max(np.abs(actual - expected))),
            "provider": "CPUExecutionProvider", "rtol": 1e-3, "atol": 1e-3}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/datasets/drone_fire_bulb_v2/data.yaml")
    parser.add_argument("--initial", type=Path, default=ROOT / "deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--device", default="0")
    parser.add_argument("--name", default="dnb26_drone_fire_bulb_yolo11n_v1")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--resume-reason", default="manual resume")
    parser.add_argument("--finalize-only", action="store_true",
                        help="Audit an already trained/evaluated checkpoint without retraining")
    args = parser.parse_args()

    import torch
    import ultralytics
    from ultralytics import YOLO

    if args.device != "cpu" and not torch.cuda.is_available():
        raise RuntimeError("CUDA training requested but unavailable; use the isolated CUDA environment")
    if not args.data.is_file() or not args.initial.is_file():
        raise FileNotFoundError("Dataset YAML and initial checkpoint must exist")

    output = ROOT / "deploy_export/weights"
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "dnb26_drone_fire_bulb_yolo11n_metadata.json"
    if args.finalize_only:
        report = finalize_training_report(report_path, imgsz=args.imgsz, batch=args.batch,
                                          device=args.device, workers=args.workers, run_name=args.name)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return
    if report_path.exists() and not args.resume_checkpoint:
        raise FileExistsError("Refusing to overwrite an existing published experiment report")
    report = json.loads(report_path.read_text(encoding="utf-8")) if args.resume_checkpoint else {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "torch": torch.__version__, "ultralytics": ultralytics.__version__,
        "cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        "initial_checkpoint": str(args.initial), "initial_sha256": sha256(args.initial),
        "names": NAMES, "data_yaml": str(args.data),
        "dataset_manifest_sha256": sha256(args.data.parent / "manifest.json"),
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "limitations": ["Prototype training; independent hardware-camera evaluation is still required",
                         "Exact/perceptual duplicate checks do not prove source-scene independence",
                         "Held-out test currently measures the new bulb class; existing classes use their prior validation split"],
    }
    if args.resume_checkpoint:
        if not args.resume_checkpoint.is_file() or report.get("checkpoint"):
            raise ValueError("Resume requires an unfinished experiment and an existing last.pt")
        if report["initial_sha256"] != sha256(args.initial) or report["dataset_manifest_sha256"] != sha256(args.data.parent / "manifest.json"):
            raise ValueError("Cannot resume after the initial model or dataset manifest changed")
        report.setdefault("resume_events", []).append({
            "at": datetime.now(timezone.utc).isoformat(), "checkpoint": str(args.resume_checkpoint),
            "checkpoint_sha256": sha256(args.resume_checkpoint), "workers": args.workers,
            "batch": args.batch, "reason": args.resume_reason,
        })
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.skip_baseline and not args.resume_checkpoint:
        baseline = YOLO(str(args.initial))
        report["baseline_old_classes"] = metrics_summary(baseline.val(
            data=str(ROOT / "data/datasets/drone_fire_extinguisher/data.yaml"),
            imgsz=args.imgsz, batch=args.batch, device=args.device, workers=args.workers,
            project=str(ROOT / "runs/detect"), name=args.name + "_baseline", plots=False,
        ))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        del baseline
        torch.cuda.empty_cache()

    model = YOLO(str(args.resume_checkpoint or args.initial))
    model.train(
        data=str(args.data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=args.device, workers=args.workers, project=str(ROOT / "runs/detect"),
        name=args.name, seed=26, deterministic=True, patience=10, optimizer="AdamW",
        lr0=0.001, lrf=0.05, close_mosaic=5, pretrained=True,
        cache=False, amp=True, plots=True,
        resume=str(args.resume_checkpoint) if args.resume_checkpoint else False,
    )
    best_path = Path(model.trainer.best)
    target = output / "dnb26_drone_fire_bulb_yolo11n_best.pt"
    if target.exists():
        raise FileExistsError(f"Refusing to replace a checkpoint: {target}")
    shutil.copy2(best_path, target)
    best = YOLO(str(target))
    if best.names != NAMES:
        raise RuntimeError(f"Unexpected class mapping: {best.names}")
    report["validation"] = metrics_summary(best.val(
        data=str(args.data), split="val", imgsz=args.imgsz, batch=args.batch,
        device=args.device, workers=args.workers, project=str(ROOT / "runs/detect"),
        name=args.name + "_validation", plots=True,
    ))
    report["held_out_bulb_test"] = metrics_summary(best.val(
        data=str(args.data), split="test", imgsz=args.imgsz, batch=args.batch,
        device=args.device, workers=args.workers, project=str(ROOT / "runs/detect"),
        name=args.name + "_bulb_test", plots=True,
    ))
    report["checkpoint"] = {"path": str(target), "sha256": sha256(target), "bytes": target.stat().st_size}
    # Always leave the trained checkpoint and metrics even if optional export fails.
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.skip_export:
        exported = Path(best.export(format="onnx", imgsz=args.imgsz, opset=12,
                                    dynamic=False, simplify=False, device="cpu"))
        report["onnx"] = {"path": str(exported), "sha256": sha256(exported), "bytes": exported.stat().st_size}
        report["onnx_validation"] = verify_onnx(target, exported)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report = finalize_training_report(report_path, imgsz=args.imgsz, batch=args.batch,
                                      device=args.device, workers=args.workers, run_name=args.name)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
