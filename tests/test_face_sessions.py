from backend.vision.face_service import FaceSession


def test_large_photo_inference_is_bounded_and_boxes_use_original_coordinates(monkeypatch):
    import sys
    from types import SimpleNamespace
    import numpy as np
    from backend.vision.face_service import FaceService

    shapes = []
    def locations(rgb, model):
        shapes.append(rgb.shape)
        assert rgb.flags.c_contiguous
        assert max(rgb.shape[:2]) <= 800
        return [(10, 200, 100, 20)]

    encoding = np.zeros(128)
    service = FaceService(SimpleNamespace(face_tolerance=.45), None)
    service.library = SimpleNamespace(face_locations=locations,
        face_encodings=lambda rgb, boxes:[encoding])
    service.predictor = object()
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace())
    image = np.zeros((2400, 1200, 3), dtype=np.uint8)
    service.encode_registration(image)
    result = service.analyze(image, live=False)
    assert shapes == [(800, 400, 3), (800, 400, 3)]
    assert result[0]['bbox'] == [60, 30, 600, 300]
    assert not result[0]['access_granted']


def test_live_camera_keeps_native_resolution_and_box_coordinates(monkeypatch):
    import sys
    from types import SimpleNamespace
    import numpy as np
    from backend.vision.face_service import FaceService

    shapes = []
    def locations(rgb, model):
        shapes.append(rgb.shape)
        return []

    service = FaceService(SimpleNamespace(face_tolerance=.45), None)
    service.library = SimpleNamespace(face_locations=locations,
        face_encodings=lambda rgb, boxes:[])
    service.predictor = object()
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace())
    assert service.analyze(np.zeros((480, 640, 3), dtype=np.uint8), live=True) == []
    assert shapes == [(480, 640, 3)]


def test_registration_and_live_inference_never_share_native_model_concurrently(monkeypatch):
    import sys
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    import numpy as np
    from backend.vision.face_service import FaceService

    guard = threading.Lock()
    active = peak = 0
    started = threading.Event()
    def locations(rgb, model):
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        started.set()
        time.sleep(.05)
        with guard:
            active -= 1
        return [(10, 50, 50, 10)]

    service = FaceService(SimpleNamespace(face_tolerance=.45), None)
    service.library = SimpleNamespace(face_locations=locations,
        face_encodings=lambda rgb, boxes:[np.zeros(128)])
    service.predictor = object()
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace())
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    with ThreadPoolExecutor(max_workers=2) as pool:
        registration = pool.submit(service.encode_registration, image)
        assert started.wait(1)
        verification = pool.submit(service.analyze, image, live=False)
        registration.result(timeout=2)
        verification.result(timeout=2)
    assert peak == 1


def test_photo_never_grants_even_when_identity_matches():
    session = FaceSession()
    result = session.observe('u1', .3, face_count=1, now=1, live=False)
    assert result['identity_matched']
    assert not result['access_granted']
    assert result['liveness_status'] == 'unavailable'


def test_blink_requires_closed_then_open_and_only_grants_once():
    session = FaceSession(closed_frames=2)
    assert not session.observe('u1', .3, now=1)['access_granted']
    assert not session.observe('u1', .1, now=1.1)['access_granted']
    assert not session.observe('u1', .1, now=1.2)['access_granted']
    assert session.observe('u1', .3, now=1.3)['access_granted']
    assert not session.observe('u1', .3, now=1.4)['new_grant']


def test_person_switch_unknown_multiple_and_absence_reset_session():
    for transition in [('u2', 1), (None, 1), ('u1', 2), (None, 0)]:
        session = FaceSession(closed_frames=1)
        session.observe('u1', .3, now=1)
        session.observe('u1', .1, now=1.1)
        assert session.observe('u1', .3, now=1.2)['access_granted']
        session.observe(transition[0], .3, face_count=transition[1], now=1.3)
        assert not session.observe('u1', .3, now=1.4)['access_granted']


def test_timeout_and_long_gaps_do_not_inherit_blink():
    session = FaceSession(closed_frames=1, max_gap=.5, timeout=2)
    session.observe('u1', .3, now=1)
    session.observe('u1', .1, now=1.1)
    assert not session.observe('u1', .3, now=2)['access_granted']


def test_closed_initial_eye_does_not_count_as_blink():
    session = FaceSession(closed_frames=1)
    session.observe('u1', .1, now=1)
    assert not session.observe('u1', .3, now=1.1)['access_granted']
