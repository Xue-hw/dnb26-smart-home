"""Evaluation reports must preserve semantic class IDs in bulb-only test sets."""

from types import SimpleNamespace
import pytest

from scripts.train_drone_fire_bulb_yolo import baseline_comparison, metrics_summary, training_summary


def test_bulb_only_metrics_are_not_mislabeled_as_drone():
    metrics = SimpleNamespace(
        box=SimpleNamespace(ap_class_index=[2], p=[0.9], r=[0.8], ap50=[0.85], ap=[0.5]),
        names={0: "drone", 1: "fire_extinguisher", 2: "light_bulb"},
        results_dict={"metrics/mAP50(B)": 0.85},
        speed={"inference": 3.2},
    )
    report = metrics_summary(metrics)
    assert set(report["per_class"]) == {"2"}
    assert report["per_class"]["2"]["name"] == "light_bulb"
    assert report["per_class"]["2"]["mAP50"] == 0.85


def test_no_ground_truth_does_not_invent_per_class_results():
    metrics = SimpleNamespace(
        box=SimpleNamespace(ap_class_index=[], p=[], r=[], ap50=[], ap=[]),
        names={0: "drone", 1: "fire_extinguisher", 2: "light_bulb"},
        results_dict={}, speed={},
    )
    assert metrics_summary(metrics)["per_class"] == {}


def test_completed_epochs_and_best_epoch_survive_resume(tmp_path):
    path = tmp_path / "results.csv"
    path.write_text("epoch, metrics/mAP50-95(B)\n1, 0.2\n2, 0.5\n3, 0.4\n")
    result = training_summary(path)
    assert result["completed_epochs"] == 3
    assert result["last_epoch"] == 3
    assert result["best_epoch_by_validation_map50_95"] == 2


def test_baseline_comparison_records_unfavorable_deltas():
    original = {"per_class": {"0": {"name": "drone", "precision": .9, "recall": .8,
                                   "mAP50": .85, "mAP50_95": .5}}}
    current = {"per_class": {"0": {"name": "drone", "precision": .8, "recall": .9,
                                  "mAP50": .8, "mAP50_95": .55}}}
    result = baseline_comparison(original, current)
    assert result["per_class"]["0"]["mAP50"]["delta"] == pytest.approx(-.05)
    assert result["per_class"]["0"]["mAP50_95"]["delta"] == pytest.approx(.05)


def test_baseline_comparison_rejects_class_mapping_change():
    with pytest.raises(ValueError, match="mismatched"):
        baseline_comparison({"per_class": {"0": {"name": "drone"}}},
                            {"per_class": {"0": {"name": "light_bulb"}}})
