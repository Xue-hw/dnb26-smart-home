from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


def test_weighting_keeps_original_samples_and_only_repeats_training_bulbs(tmp_path):
    from scripts.refine_bulb_model import weighted_training_paths
    paths = [tmp_path / name for name in ('bulb.jpg', 'drone.jpg', 'negative.jpg')]
    labels = {paths[0]: {2}, paths[1]: {0}, paths[2]: set()}
    result = weighted_training_paths(paths, labels, {paths[2]}, bulb_repeat=3)
    assert result.count(paths[0]) == 3
    assert result.count(paths[1]) == 1
    assert result.count(paths[2]) == 3
    assert set(result) == set(paths)


def test_approved_negative_must_be_an_existing_nonbulb_training_image(tmp_path):
    from scripts.refine_bulb_model import weighted_training_paths
    bulb = tmp_path / 'bulb.jpg'
    with pytest.raises(ValueError):
        weighted_training_paths([bulb], {bulb: {2}}, {bulb})
    with pytest.raises(ValueError):
        weighted_training_paths([bulb], {bulb: {2}}, {Path('held_out.jpg')})


def test_mining_does_not_eagerly_decode_all_training_images(tmp_path, monkeypatch):
    from scripts.refine_bulb_model import mine
    source = tmp_path / 'source'
    (source / 'images/train').mkdir(parents=True)
    (source / 'labels/train').mkdir(parents=True)
    for index in range(20):
        (source / f'images/train/{index}.jpg').write_bytes(b'fixture')
        (source / f'labels/train/{index}.txt').write_text('')
    class Model:
        def __init__(self, path):
            pass
        def predict(self, *, source, **kwargs):
            assert len(source) <= 8, 'Ultralytics eagerly decodes list inputs; bound the list'
            return [SimpleNamespace(boxes=[]) for path in source]
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=Model))
    checkpoint = tmp_path / 'old.pt'
    checkpoint.write_bytes(b'old checkpoint')
    mine(SimpleNamespace(source=source, checkpoint=checkpoint, output=tmp_path/'mining'))


def test_candidate_images_are_independent_copies_not_source_hardlinks(tmp_path):
    from scripts.refine_bulb_model import prepare
    source = tmp_path / 'source'
    for index, split in enumerate(('train','val','test')):
        (source / f'images/{split}').mkdir(parents=True)
        (source / f'labels/{split}').mkdir(parents=True)
        (source / f'images/{split}/image.jpg').write_bytes(f'original {index}'.encode())
        (source / f'labels/{split}/image.txt').write_text('2 .5 .5 .2 .2\n')
    prepare(SimpleNamespace(source=source, output=tmp_path/'candidate', approved_negatives=None))
    (tmp_path/'candidate/dataset/images/train/image.jpg').write_bytes(b'library repair')
    assert (source/'images/train/image.jpg').read_bytes()==b'original 0'


def test_fixed_working_point_counts_duplicate_predictions_as_false_positives():
    from scripts.refine_bulb_model import match_counts
    assert match_counts([[0,0,10,10], [0,0,10,10], [20,20,30,30]], [[0,0,10,10]]) == (1,2,0)
    assert match_counts([], [[0,0,10,10]]) == (0,0,1)


@pytest.mark.parametrize('crop_box,valid', [([0,0,40,40],True),([70,70,99,99],False),([-1,0,40,40],False)])
def test_background_crops_preserve_train_group_and_reject_targets(tmp_path,crop_box,valid):
    import json
    from PIL import Image
    from scripts.refine_bulb_model import prepare
    source=tmp_path/'source'
    for index,split in enumerate(('train','val','test')):
        (source/f'images/{split}').mkdir(parents=True)
        (source/f'labels/{split}').mkdir(parents=True)
        Image.new('RGB',(100,100),(index*40,0,0)).save(source/f'images/{split}/image.jpg')
        (source/f'labels/{split}/image.txt').write_text('0 .8 .8 .3 .3\n')
    approved=tmp_path/'approved.json'
    approved.write_text(json.dumps([str((source/'images/train/image.jpg').resolve())]))
    crops=tmp_path/'crops.json'
    crops.write_text(json.dumps([{'source':str((source/'images/train/image.jpg').resolve()),'box':crop_box,'review_note':'fixture'}]))
    args=SimpleNamespace(source=source,output=tmp_path/'candidate',approved_negatives=approved,approved_crops=crops)
    if not valid:
        with pytest.raises(ValueError):
            prepare(args)
    else:
        data=prepare(args)
        assert (data.parent/'labels/train/reviewed_negative_crop_0.txt').read_bytes()==b''
        assert not list((data.parent/'images/val').glob('*crop*'))


def test_fixed_metrics_preserve_float32_threshold_equalities():
    import numpy as np
    from scripts.refine_bulb_model import threshold_predictions, inference_floor
    for threshold in (.5,.7):
        exact=float(np.float32(threshold))
        lower=float(np.nextafter(np.float32(threshold),np.float32('-inf')))
        rows=[[0,0,10,10,exact,2],[10,10,20,20,lower,2]]
        assert threshold_predictions(rows,2,threshold)==[[0,0,10,10]]
    assert inference_floor()==float(np.nextafter(np.float32(.5),np.float32('-inf')))


def test_training_reloads_unfused_weights_after_baseline_evaluation(tmp_path,monkeypatch):
    import scripts.refine_bulb_model as refinement
    import scripts.train_drone_fire_bulb_yolo as original
    class Model:
        def __init__(self,path): self.fused=False
        def val(self,**kwargs): self.fused=True;return None
        def train(self,**kwargs):
            assert not self.fused,'Baseline validation can fuse in place; never train that object'
            raise RuntimeError('fresh-train-marker')
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(__version__='fixture',cuda=SimpleNamespace(is_available=lambda:True,empty_cache=lambda:None)))
    monkeypatch.setitem(sys.modules,'ultralytics',SimpleNamespace(__version__='fixture',YOLO=Model))
    monkeypatch.setattr(original,'metrics_summary',lambda result:{})
    monkeypatch.setattr(refinement,'fixed_metrics',lambda *args:{})
    output=tmp_path/'output'
    output.mkdir()
    checkpoint=tmp_path/'old.pt'
    checkpoint.write_bytes(b'old')
    monkeypatch.setattr(refinement,'prepare',lambda args:tmp_path/'dataset/data.yaml')
    with pytest.raises(RuntimeError,match='fresh-train-marker'):
        refinement.train(SimpleNamespace(checkpoint=checkpoint,output=output,prepared_data=None,epochs=15))
