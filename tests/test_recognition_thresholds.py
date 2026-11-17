"""Candidate thresholds are engineering tests, not real-person access acceptance."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from backend.config import Settings
from backend.vision.ascend_service import decode_predictions
from backend.vision.face_service import FaceService
from backend.vision.model_service import ModelService


def test_runtime_defaults_and_environment_threshold_override(monkeypatch):
    assert Settings().confidence == .70
    assert Settings().face_tolerance == .35
    monkeypatch.setenv('DNB_CONFIDENCE', '.8')
    monkeypatch.setenv('DNB_FACE_TOLERANCE', '.2')
    config = Settings.from_env()
    assert (config.confidence, config.face_tolerance) == (.8, .2)


@pytest.mark.parametrize('field', ['confidence', 'face_tolerance'])
@pytest.mark.parametrize('value', [-.1, 1.1, float('nan'), float('inf')])
def test_invalid_recognition_thresholds_are_rejected(field, value):
    with pytest.raises(ValueError):
        Settings(**{field: value})


@pytest.mark.parametrize(('distance', 'matched'), [(.2999, True), (.30, True), (.3001, False), (.45, False)])
def test_face_similarity_070_boundary_still_never_grants_static_photo(monkeypatch, distance, matched):
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace())
    service = FaceService(SimpleNamespace(face_tolerance=.30), None)
    encoding = np.zeros(128)
    service.people = [({'user_id': 'known', 'name': 'Known'}, encoding)]
    service.library = SimpleNamespace(face_locations=lambda rgb, model: [(0, 20, 20, 0)],
        face_encodings=lambda rgb, boxes: [encoding], face_distance=lambda people, query: np.array([distance]))
    service.predictor = object()
    result = service.analyze(np.zeros((32, 32, 3), dtype=np.uint8), live=False)[0]
    assert result['identity_matched'] is matched
    assert result['similarity'] == pytest.approx(1. - distance)
    assert result['access_granted'] is False
    assert result['liveness_status'] == 'unavailable'


def test_ascend_includes_float32_070_boundary_but_not_previous_float():
    threshold = np.float32(.70)
    scores = [np.nextafter(threshold, np.float32(-np.inf)), threshold, np.nextafter(threshold, np.float32(np.inf))]
    rows = [[20 + i*30, 20, 10, 10, score] for i, score in enumerate(scores)]
    result = decode_predictions(np.array(rows, dtype=np.float32).T[None], ['car'], (100, 100, 3), 1, (0, 0), confidence=.70)
    assert len(result) == 2
    assert {r['confidence'] for r in result} == {float(scores[1]), float(scores[2])}


@pytest.mark.parametrize('backend', ['cpu', 'ascend'])
def test_both_object_backends_enforce_same_threshold_and_keep_original_scores(backend):
    threshold = np.float32(.70)
    scores = [np.nextafter(threshold, np.float32(-np.inf)), threshold, np.nextafter(threshold, np.float32(np.inf))]
    calls = []
    if backend == 'cpu':
        def predict(image, **options):
            calls.append(options['conf'])
            # The upstream YOLO NMS uses strict >, so the entry threshold must include .70.
            boxes = [SimpleNamespace(cls=[0], conf=[score], xyxy=[np.array([1, 2, 3, 4])])
                     for score in scores if score > np.float32(options['conf'])]
            return [SimpleNamespace(names={0: 'car'}, boxes=boxes)]
        model = SimpleNamespace(predict=predict)
    else:
        def detect(image, confidence):
            calls.append(confidence)
            return [{'label': 'car', 'confidence': float(score), 'bbox': [1, 2, 3, 4]} for score in scores]
        model = SimpleNamespace(detect=detect)
    service = ModelService(Settings(confidence=.70))
    service.models = [('general', model)]
    service.states = [{'name': 'general', 'backend': backend, 'status': 'online', 'classes': ['car']}]
    result, _ = service.detect(np.zeros((20, 20, 3), dtype=np.uint8))
    assert len(result) == 2
    assert {r['confidence'] for r in result} == {float(scores[1]), float(scores[2])}
    assert len(calls) == 1


def test_general_exclusions_preserve_custom_drone_extinguisher_and_general_people_cars():
    def detector(labels):
        return SimpleNamespace(detect=lambda image, confidence: [
            {'label': label, 'confidence': .9, 'bbox': [1, 2, 3, 4]} for label in labels])
    service = ModelService(Settings())
    service.models = [('custom', detector(['drone', 'fire_extinguisher'])),
                      ('general', detector(['airplane', 'drone', 'vase', 'person', 'car']))]
    service.states = [
        {'name': 'custom', 'backend': 'ascend', 'status': 'online', 'classes': ['drone', 'fire_extinguisher']},
        {'name': 'general', 'backend': 'ascend', 'status': 'online', 'classes': ['airplane', 'drone', 'vase', 'person', 'car']},
    ]
    results, _ = service.detect(np.zeros((20, 20, 3), dtype=np.uint8))
    assert {(r['model'], r['label']) for r in results} == {
        ('custom', 'drone'), ('custom', 'fire_extinguisher'), ('general', 'person'), ('general', 'car')}


def test_general_drone_stays_disabled_even_if_custom_model_is_unavailable():
    service = ModelService(Settings())
    service.models = [('general', SimpleNamespace(detect=lambda image, confidence: [
        {'label': label, 'confidence': .9, 'bbox': [1, 2, 3, 4]} for label in ['drone', 'airplane', ' Vase ', 'car']]))]
    service.states = [{'name': 'custom', 'backend': 'ascend', 'status': 'offline', 'classes': ['drone']},
                      {'name': 'general', 'backend': 'ascend', 'status': 'online', 'classes': ['drone', 'airplane', 'vase', 'car']}]
    results, _ = service.detect(np.zeros((20, 20, 3), dtype=np.uint8))
    assert [r['label'] for r in results] == ['car']


@pytest.mark.parametrize(('distance', 'matched'), [(.3499, True), (.35, True), (.3501, False)])
def test_face_similarity_065_trial_default_rejects_below_cutoff_without_static_access(monkeypatch, distance, matched):
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace())
    service = FaceService(Settings(), None)
    encoding = np.zeros(128)
    service.people = [({'user_id': 'known', 'name': 'Known'}, encoding)]
    service.library = SimpleNamespace(face_locations=lambda rgb, model: [(0, 20, 20, 0)],
        face_encodings=lambda rgb, boxes: [encoding], face_distance=lambda people, query: np.array([distance]))
    service.predictor = object()
    result = service.analyze(np.zeros((32, 32, 3), dtype=np.uint8), live=False)[0]
    assert result['identity_matched'] is matched
    assert result['match_threshold'] == pytest.approx(.65)
    assert not result['access_granted'] and not result['new_grant']
