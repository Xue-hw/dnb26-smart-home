from scripts.audit_drone_fire_bulb_dataset import intersections


def test_audit_distinguishes_exact_and_perceptual_neighbors():
    training = {"train_exact": ("same_pixels", 0), "train_similar": ("different_pixels", 3),
                "train_other": ("other_pixels", 255)}
    validation = {"val": ("same_pixels", 0)}
    result = intersections(training, validation)
    assert result["exact_pixel_pair_count"] == 1
    assert result["dhash_pair_count"] == 2
    assert result["validation_images_with_dhash_neighbor"] == 1
    assert result["training_images_with_dhash_neighbor"] == 2
    assert result["exact_pixel_pairs"] == [{"validation": "val", "training": "train_exact"}]


def test_audit_keeps_counts_when_examples_are_bounded():
    training = {str(index): (str(index), 0) for index in range(150)}
    result = intersections(training, {"val": ("no_pixel_match", 0)})
    assert result["dhash_pair_count"] == 150
    assert len(result["dhash_pair_examples_first_100"]) == 100
    assert result["exact_pixel_pair_count"] == 0
