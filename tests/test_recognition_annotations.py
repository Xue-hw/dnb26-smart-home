"""Semantic overlay colors must agree across live JPEGs and photo canvases."""
import time

import cv2
import numpy as np

from backend.config import Settings
from backend.runtime import Runtime


def test_live_overlay_uses_model_source_and_face_decision(tmp_path, monkeypatch):
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='mock'))
    runtime.options['bulb_linkage'] = False
    runtime.last_recognition = time.monotonic()
    runtime.models.detect = lambda frame: ([
        {'model': 'general', 'label': 'person', 'confidence': .8, 'bbox': [1, 2, 8, 9]},
        {'model': 'custom', 'label': 'drone', 'confidence': .9, 'bbox': [2, 3, 9, 10]},
    ], 1.)
    runtime.face_state = {'frame_id': 1, 'captured_at': None, 'faces': [
        {'bbox': [0, 0, 5, 5], 'identity_matched': True,
         'liveness_status': 'passed', 'access_granted': True},
        {'bbox': [5, 5, 10, 10], 'identity_matched': False,
         'liveness_status': 'pending', 'access_granted': False},
    ]}
    colors, labels = [], []
    monkeypatch.setattr(cv2, 'rectangle', lambda frame, start, end, color, width: colors.append(color))
    monkeypatch.setattr(cv2, 'putText', lambda frame, text, *args: labels.append(text))
    runtime.process_frame(np.zeros((16, 16, 3), dtype=np.uint8), 1, None, True)
    assert colors == [(74, 163, 22), (38, 38, 220), (235, 99, 37), (237, 58, 124)]
    assert any('GENERAL' in label for label in labels)
    assert any('CUSTOM' in label for label in labels)
    assert any('UNAUTHORIZED' in label for label in labels)


def test_face_styles_never_infer_liveness_or_permission_from_one_field():
    from backend.vision.annotations import face_annotation
    def style(identity, live, access):
        return face_annotation({'identity_matched': identity, 'liveness_status': live,
                                'access_granted': access})[0]
    assert style(True, 'passed', True) == 'face_granted'
    assert style(True, 'passed', False) == 'face_live'
    assert style(True, 'pending', True) == 'face_pending'
    assert style(True, 'unavailable', False) == 'face_unavailable'
    assert style(True, 'failed', False) == 'face_failed'
    assert style(True, 'timeout', False) == 'face_failed'
    assert style(False, 'passed', True) == 'face_unauthorized'
    assert style(None, None, True) == 'unknown'
