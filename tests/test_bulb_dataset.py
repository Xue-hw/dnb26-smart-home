"""Dataset integrity guards for the three-class training extension."""

import hashlib

import pytest

from scripts.build_drone_fire_bulb_dataset import (
    box_to_yolo,
    canonical_fingerprint,
    classify_split,
    assign_bulb_split,
    validate_label,
)


def test_openimages_box_maps_to_new_class_without_inventing_annotations():
    row = {"XMin": "0.1", "XMax": "0.6", "YMin": "0.2", "YMax": "0.8"}
    assert box_to_yolo(row) == "2 0.350000 0.500000 0.500000 0.600000"


@pytest.mark.parametrize("row", [
    {"XMin": "0.8", "XMax": "0.2", "YMin": "0.2", "YMax": "0.8"},
    {"XMin": "-0.1", "XMax": "0.6", "YMin": "0.2", "YMax": "0.8"},
])
def test_invalid_boxes_fail_loudly(row):
    with pytest.raises(ValueError):
        box_to_yolo(row)


def test_split_is_deterministic_and_reserves_validation_and_test():
    splits = [classify_split(hashlib.sha256(str(i).encode()).hexdigest()) for i in range(1000)]
    assert set(splits) == {"train", "val", "test"}
    assert splits == [classify_split(hashlib.sha256(str(i).encode()).hexdigest()) for i in range(1000)]
    assert 650 < splits.count("train") < 850


def test_decoded_pixels_detect_different_jpeg_encodings(tmp_path):
    from PIL import Image

    image = Image.new("RGB", (12, 12), color="red")
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    image.save(first, compress_level=1)
    image.save(second, compress_level=9)
    assert first.read_bytes() != second.read_bytes()
    assert canonical_fingerprint(first) == canonical_fingerprint(second)


@pytest.mark.parametrize("label", ["3 .5 .5 .2 .2", "2 .5 .5 0 .2", "2 nan .5 .2 .2"])
def test_invalid_yolo_label_is_rejected(label):
    with pytest.raises(ValueError):
        validate_label(label)


def test_existing_two_classes_remain_valid():
    for label in ("0 .5 .5 .2 .3", "1 .5 .5 .4 .5", "2 .5 .5 .4 .5"):
        validate_label(label)


def test_similar_bulb_images_cannot_cross_splits(tmp_path):
    from PIL import Image

    image = Image.new("RGB", (12, 12), color="red")
    path = tmp_path / "bulb.png"
    image.save(path)
    groups = []
    first = assign_bulb_split(path, "image-a", groups)
    second = assign_bulb_split(path, "different-fingerprint", groups)
    assert first == second
    assert len(groups) == 1
