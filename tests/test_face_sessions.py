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


def test_person_switch_multiple_and_absence_reset_session():
    for transition in [('u2', 1), ('u1', 2), (None, 0)]:
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


def test_default_window_allows_blink_after_twelve_seconds():
    session = FaceSession(closed_frames=1)
    for now in range(1, 15):
        result = session.observe('u1', .3, now=now)
    assert result['verification_remaining_seconds'] == 2
    session.observe('u1', .1, now=14.2)
    assert session.observe('u1', .3, now=14.4)['new_grant']


def test_temporary_mismatch_preserves_blink_but_never_grants_without_current_match():
    session = FaceSession(closed_frames=1)
    session.observe('u1', .3, now=1)
    session.observe('u1', .1, now=1.1)
    result = session.observe(None, .1, now=1.2)
    assert result['identity_recheck'] is True
    assert result['identity_matched'] is False and result['user_id'] is None
    assert not result['access_granted'] and not result['new_grant']
    result = session.observe('u1', .3, now=1.3)
    assert result['verification_remaining_seconds'] == 15
    assert result['access_granted'] and result['new_grant']
    session.observe('u1', .1, now=1.4)
    assert not session.observe('u1', .3, now=1.5)['new_grant']


def test_mismatch_cannot_extend_deadline_expose_pass_or_reissue_command():
    session = FaceSession(closed_frames=1, timeout=3)
    session.observe('u1', .3, now=1)
    session.observe('u1', .1, now=1.1)
    assert session.observe('u1', .3, now=1.2)['new_grant']
    session.command_id = 'old-command'
    for now in (1.5, 2.5, 3.5):
        result = session.observe(None, .3, now=now)
        assert result['identity_recheck'] and not result['access_granted']
        assert result.get('command_id') is None
    result = session.observe('u1', .3, now=4)
    assert result['liveness_status'] == 'timeout'
    assert result['verification_remaining_seconds'] == 0
    assert not result['access_granted']
    result = session.observe('u1', .3, now=4.1)
    assert result['verification_remaining_seconds'] == 3
    assert not result['access_granted']


def test_unknown_without_prior_match_and_long_gap_do_not_enter_recheck():
    session = FaceSession()
    assert not session.observe(None, .3, now=1).get('identity_recheck', False)
    session.observe('u1', .3, now=2)
    assert not session.observe(None, .3, now=4).get('identity_recheck', False)


def test_switch_multiple_absence_and_static_do_not_inherit_recheck():
    for identity, count in [('u2',1),('u1',2),(None,0)]:
        session = FaceSession(closed_frames=1)
        session.observe('u1', .3, now=1)
        session.observe(None, .3, now=1.1)
        result = session.observe(identity, .3, face_count=count, now=1.2)
        assert not result.get('identity_recheck',False)
        assert not result['access_granted']
        assert not session.observe('u1',.3,now=1.3)['access_granted']


def test_identity_mismatch_keeps_same_wait_message_and_original_fifteen_second_deadline():
    session = FaceSession()
    session.observe('u1', .3, now=1)
    for now in (2, 3, 4, 5):
        result = session.observe(None, .1, now=now)
        assert result['reason'] == '活体验证中'
        assert result['liveness_status'] == 'pending'
        assert result['verification_remaining_seconds'] == 16 - now
        assert session.started == 1
        assert not result['identity_matched'] and result['user_id'] is None
        assert not result['access_granted'] and not result['new_grant']
    result = session.observe('u1', .3, now=6)
    assert result['verification_remaining_seconds'] == 10
    assert result['access_granted'] and result['new_grant']
    for now in range(7, 16):
        result = session.observe(None, .3, now=now)
    result = session.observe(None, .3, now=16)
    assert result['liveness_status'] == 'timeout'
    assert not result['access_granted']


def test_default_low_fps_blink_requires_only_one_closed_processed_frame():
    session = FaceSession()
    assert session.closed_frames == 1
    assert not session.observe('u1', .3, now=1)['access_granted']
    assert not session.observe('u1', .1, now=1.8)['access_granted']
    assert session.observe('u1', .3, now=2.6)['new_grant']


def test_blink_can_finish_during_score_dip_but_grant_waits_for_original_current_identity():
    session = FaceSession()
    session.observe('u1', .3, now=1)
    for ear, now in [(.1, 1.7), (.3, 2.4)]:
        result = session.observe(None, ear, now=now)
        assert result['identity_recheck'] and not result['identity_matched']
        assert result['user_id'] is None and not result['access_granted'] and not result['new_grant']
    result = session.observe('u1', .3, now=3.1)
    assert result['user_id'] == 'u1' and result['access_granted'] and result['new_grant']
    assert session.started == 1


def test_rematch_while_closed_does_not_grant_until_current_matched_open_eye():
    session = FaceSession()
    session.observe('u1', .3, now=1)
    session.observe(None, .1, now=1.5)
    session.observe(None, .3, now=2)
    assert not session.observe('u1', .1, now=2.5)['new_grant']
    assert session.observe('u1', .3, now=3)['new_grant']


def test_switch_or_discontinuity_discards_completed_blink_before_rematch():
    for identity, count, ear, gap in [('u2', 1, .3, .5), (None, 0, .3, .5),
                                      ('u1', 2, .3, .5), ('u1', 1, None, .5),
                                      ('u1', 1, float('nan'), .5), ('u1', 1, .3, 2)]:
        session = FaceSession()
        session.observe('u1', .3, now=1)
        session.observe(None, .1, now=1.5)
        session.observe(None, .3, now=2)
        assert not session.observe(identity, ear, face_count=count, now=2+gap)['new_grant']
        assert not session.observe('u1', .3, now=2+gap+.1)['new_grant']


def test_passed_session_does_not_issue_second_grant_after_score_dip():
    session = FaceSession()
    session.observe('u1', .3, now=1)
    session.observe('u1', .1, now=1.5)
    assert session.observe('u1', .3, now=2)['new_grant']
    session.command_id = 'first-command'
    result = session.observe(None, .3, now=2.5)
    assert not result['access_granted'] and result.get('command_id') is None
    session.observe(None, .1, now=3)
    result = session.observe('u1', .3, now=3.5)
    assert result['access_granted'] and not result['new_grant']
    assert result['command_id'] == 'first-command'


def test_constant_open_or_initial_closed_never_grants_without_full_blink():
    for initial in (.1, .3):
        session = FaceSession()
        session.observe('u1', initial, now=1)
        assert not session.observe(None, initial, now=1.5)['new_grant']
        assert not session.observe('u1', .3, now=2)['new_grant']


def test_completed_blink_does_not_survive_timeout_to_grant_on_late_match():
    session = FaceSession(timeout=3)
    session.observe('u1', .3, now=1)
    session.observe(None, .1, now=1.5)
    session.observe(None, .3, now=2)
    session.observe(None, .3, now=3)
    result = session.observe('u1', .3, now=4)
    assert result['liveness_status'] == 'timeout' and not result['new_grant']
    assert not session.observe('u1', .3, now=4.1)['new_grant']


def test_box_discontinuity_cannot_transfer_completed_blink_to_a_new_location(monkeypatch):
    import sys
    from types import SimpleNamespace
    import numpy as np
    import backend.vision.face_service as module
    from backend.config import Settings
    from backend.vision.face_service import FaceService

    state = {'box': (10, 40, 40, 10), 'distance': .2, 'ear': .3}
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace(rectangle=lambda *coordinates: coordinates))
    monkeypatch.setattr(module, '_ear', lambda points: state['ear'])
    service = FaceService(Settings(), None)
    encoding = np.zeros(128)
    service.people = [({'user_id': 'u1', 'name': 'Known'}, encoding)]
    service.library = SimpleNamespace(face_locations=lambda rgb, model: [state['box']],
        face_encodings=lambda rgb, boxes: [encoding],
        face_distance=lambda people, query: np.array([state['distance']]))
    service.predictor = lambda rgb, rectangle: SimpleNamespace(part=lambda i: SimpleNamespace(x=i, y=i))
    image = np.zeros((120, 120, 3), dtype=np.uint8)
    service.analyze(image, live=True)
    state.update(distance=.4, ear=.1)
    assert not service.analyze(image, live=True)[0]['new_grant']
    state.update(ear=.3)
    assert not service.analyze(image, live=True)[0]['new_grant']
    assert service.session.blink_completed
    state.update(distance=.2, box=(70, 110, 110, 70))
    result = service.analyze(image, live=True)[0]
    assert result['identity_matched'] and not result['new_grant']
    assert not service.session.blink_completed


def test_eye_threshold_boundary_still_requires_an_actual_open_closed_open_transition():
    session = FaceSession()
    assert not session.observe('u1', .23, now=1)['new_grant']
    assert not session.observe('u1', .23, now=1.5)['new_grant']
    assert not session.observe('u1', .2299, now=2)['new_grant']
    assert session.observe('u1', .23, now=2.5)['new_grant']


def _feature_continuity_fixture(monkeypatch):
    import sys
    from types import SimpleNamespace
    import numpy as np
    import backend.vision.face_service as module
    from backend.config import Settings
    from backend.vision.face_service import FaceService

    state = {'feature': .31, 'ear': .3}
    monkeypatch.setitem(sys.modules, 'dlib', SimpleNamespace(rectangle=lambda *coordinates: coordinates))
    monkeypatch.setattr(module, '_ear', lambda points: state['ear'])
    service = FaceService(Settings(), None)
    reference = np.zeros(128)
    service.people = [({'user_id': 'u1', 'name': 'Known'}, reference)]
    def encode(rgb, boxes):
        feature = np.zeros(128)
        feature[0] = state['feature']
        return [feature]
    service.library = SimpleNamespace(face_locations=lambda rgb, model: [(10, 50, 50, 10)],
        face_encodings=encode,
        face_distance=lambda people, query: np.array([np.linalg.norm(p-query) for p in people]))
    service.predictor = lambda rgb, rectangle: SimpleNamespace(part=lambda i: SimpleNamespace(x=i, y=i))
    image = np.zeros((80, 80, 3), dtype=np.uint8)
    return service, state, image


def test_same_location_other_person_cannot_supply_blink_for_original_identity(monkeypatch):
    # Every box has IoU=1; different embeddings must still invalidate the sequence.
    for closed_feature, open_feature in [(.9, .9), (.5, .7)]:
        service, state, image = _feature_continuity_fixture(monkeypatch)
        service.analyze(image, live=True)
        state.update(feature=closed_feature, ear=.1)
        assert not service.analyze(image, live=True)[0]['new_grant']
        state.update(feature=open_feature, ear=.3)
        assert not service.analyze(image, live=True)[0]['new_grant']
        state.update(feature=.31, ear=.3)
        result = service.analyze(image, live=True)[0]
        assert result['identity_matched'] and not result['new_grant']
        assert not result['access_granted']


def test_live_feature_continuity_allows_registration_score_dip_during_blink(monkeypatch):
    service, state, image = _feature_continuity_fixture(monkeypatch)
    assert service.analyze(image, live=True)[0]['identity_matched']
    state.update(feature=.36, ear=.1)  # .64 to registration, .05 to live anchor.
    result = service.analyze(image, live=True)[0]
    assert not result['identity_matched'] and not result['new_grant']
    state.update(feature=.37, ear=.3)
    assert not service.analyze(image, live=True)[0]['new_grant']
    state.update(feature=.31, ear=.3)
    result = service.analyze(image, live=True)[0]
    assert result['identity_matched'] and result['new_grant']
