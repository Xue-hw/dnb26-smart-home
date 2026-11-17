"""Door-cycle cooldown tests; simulated telemetry is engineering evidence only."""
from backend.vision.face_gate import FaceGateCooldown


def active_gate():
    gate = FaceGateCooldown()
    token = gate.reserve(gate.generation, now=1)
    gate.bind(token, 'c1')
    gate.dispatched('c1', now=2)
    return gate, token


def test_only_one_reservation_and_open_then_close_releases():
    gate, token = active_gate()
    assert token is not None
    assert gate.reserve(gate.generation, now=3) is None
    assert not gate.observe('closed', received_at=3)
    assert gate.snapshot()['active']
    assert not gate.observe('open', received_at=4)
    assert gate.snapshot()['phase'] == 'waiting_close'
    assert gate.observe('closed', received_at=5)
    assert not gate.snapshot()['active']


def test_pre_dispatch_or_out_of_order_telemetry_cannot_release():
    gate = FaceGateCooldown()
    token = gate.reserve(0, now=2)
    gate.bind(token, 'c1')
    gate.observe('open', received_at=1)
    gate.observe('closed', received_at=1.5)
    assert gate.snapshot()['active'] and gate.snapshot()['phase'] == 'waiting_open'
    gate.dispatched('c1', now=3)
    gate.observe('open', received_at=4)
    assert not gate.observe('closed', received_at=2.5)
    assert gate.snapshot()['active']
    assert gate.observe('closed', received_at=5)
    assert not gate.observe('open', received_at=4.5)
    assert not gate.snapshot()['active']


def test_ack_does_not_release_and_failure_does_not_override_open():
    gate, _ = active_gate()
    assert not gate.command_result('c1', 'acked', now=3)
    assert not gate.command_result('old-command', 'failed', now=3)
    gate.observe('open', received_at=4)
    assert not gate.command_result('c1', 'failed', now=5)
    assert gate.snapshot()['active']
    assert gate.observe('closed', received_at=6)


def test_known_failed_command_clears_but_timeout_keeps_unknown():
    gate, _ = active_gate()
    assert not gate.command_result('c1', 'timeout', now=3)
    assert gate.snapshot()['active'] and gate.snapshot()['phase'] == 'unknown'
    assert gate.command_result('c1', 'failed', now=4)
    assert not gate.snapshot()['active']


def test_late_return_and_old_token_cannot_overwrite_next_cycle():
    gate, old_token = active_gate()
    old_epoch = gate.generation
    gate.observe('open', received_at=3)
    gate.observe('closed', received_at=4)
    assert gate.reserve(old_epoch, now=5) is None
    token = gate.reserve(gate.generation, now=5)
    gate.bind(token, 'c2')
    gate.bind(old_token, 'c1')
    assert not gate.cancel_unbound(old_token)
    assert not gate.command_result('c1', 'failed', now=6)
    assert gate.snapshot()['command_id'] == 'c2'


def test_unbound_failure_can_cancel_but_bound_outcome_is_retained():
    gate = FaceGateCooldown()
    token = gate.reserve(0, now=1)
    assert gate.cancel_unbound(token)
    token = gate.reserve(gate.generation, now=2)
    gate.bind(token, 'c1')
    assert not gate.cancel_unbound(token)


def test_existing_open_door_also_waits_for_fresh_close():
    gate = FaceGateCooldown()
    gate.observe('open', received_at=1)
    assert gate.snapshot()['active'] and gate.snapshot()['phase'] == 'waiting_close'
    assert gate.reserve(gate.generation, now=2) is None
    assert gate.observe('closed', received_at=3)


def runtime_fixture(tmp_path):
    import time
    import numpy as np
    from backend.config import Settings
    from backend.runtime import Runtime
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='serial'))
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    runtime.camera.frame = image
    runtime.camera.status = 'online'
    runtime.camera.last_frame = time.monotonic()
    runtime.repository.is_authorized = lambda uid: True
    runtime.repository.update_device = lambda *args: None
    runtime.repository.event = lambda category, payload, device_id=None: payload
    runtime.record_live_event = lambda *args: None
    capture = {'captured_monotonic':runtime.camera.last_frame, 'generation':runtime.camera.generation}
    return runtime, image, capture


def successful_face():
    return {'new_grant':True, 'user_id':'u1', 'identity_matched':True,
            'access_granted':True, 'liveness_status':'passed', 'reason':'blink'}


def test_runtime_suppresses_new_inference_until_matching_source_open_close(tmp_path):
    runtime, image, capture = runtime_fixture(tmp_path)
    calls=[]
    runtime.face.analyze=lambda frame, live:[successful_face()]
    def send(*args, **kwargs):
        calls.append(args)
        runtime.face_gate.bind(kwargs['face_gate_token'], 'gate-1')
        runtime.face_gate.dispatched('gate-1')
        return {'command_id':'gate-1', 'status':'pending'}
    runtime.send_command=send
    runtime.repository.command=lambda cid:{'command_id':cid, 'status':'pending'}
    runtime.process_faces(image, 1, 'now', True, **capture)
    assert len(calls)==1 and runtime.face_gate.snapshot()['active']
    runtime.face.analyze=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('cooldown ran inference'))
    runtime.process_faces(image, 2, 'now', True, **capture)
    runtime.face.reset_session()
    runtime.process_faces(None, 3, 'now', True, **capture)
    assert runtime.face_gate.snapshot()['active']
    def telemetry(device, position, source='serial'):
        runtime.ingest_telemetry({'device_id':device, 'state':{'position':position}},source)
    telemetry('front_door', 'closed')
    telemetry('garage_door', 'open')
    telemetry('garage_door', 'closed')
    telemetry('front_door', 'open', 'mock')
    telemetry('front_door', 'closed', 'mock')
    assert runtime.face_gate.snapshot()['active']
    telemetry('front_door','open')
    telemetry('front_door','closed')
    assert not runtime.face_gate.snapshot()['active'] and not runtime.face.session.passed


def test_late_command_return_cannot_resurrect_completed_cooldown(tmp_path):
    runtime, image, capture = runtime_fixture(tmp_path)
    runtime.face.analyze=lambda frame, live:[successful_face()]
    def send(*args, **kwargs):
        runtime.face_gate.bind(kwargs['face_gate_token'], 'gate-1')
        runtime.face_gate.dispatched('gate-1')
        runtime.ingest_telemetry({'device_id':'front_door','state':{'position':'open'}},'serial')
        runtime.ingest_telemetry({'device_id':'front_door','state':{'position':'closed'}},'serial')
        return {'command_id':'gate-1','status':'acked'}
    runtime.send_command=send
    runtime.process_faces(image,1,'now',True,**capture)
    assert not runtime.face_gate.snapshot()['active'] and runtime.face_state['faces']==[]


def test_inflight_face_from_before_open_close_never_submits_after_unlock(tmp_path):
    runtime,image,capture=runtime_fixture(tmp_path)
    def analyze(frame,live):
        runtime.ingest_telemetry({'device_id':'front_door','state':{'position':'open'}},'serial')
        runtime.ingest_telemetry({'device_id':'front_door','state':{'position':'closed'}},'serial')
        return [successful_face()]
    runtime.face.analyze=analyze
    runtime.send_command=lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('old inference submitted'))
    runtime.process_faces(image,1,'now',True,**capture)
    assert runtime.face_state['faces']==[] and not runtime.face_gate.snapshot()['active']


def test_gateway_direct_failure_and_database_error_are_reconciled(tmp_path):
    runtime, image, capture=runtime_fixture(tmp_path)
    token=runtime.face_gate.reserve(runtime.face_gate.generation)
    runtime.face_gate.bind(token,'gate-1')
    runtime.repository.command=lambda cid:(_ for _ in ()).throw(RuntimeError('database temporarily unavailable'))
    runtime.process_faces(image,1,'now',True,**capture)
    assert runtime.face_gate.snapshot()['active'] and 'face_cooldown' in runtime.errors
    runtime._face_gate_command_check_at=0
    runtime.repository.command=lambda cid:{'command_id':cid,'status':'failed'}
    runtime.face.analyze=lambda frame,live:[]
    runtime.process_faces(image,2,'now',True,**capture)
    assert not runtime.face_gate.snapshot()['active']
    assert 'face_cooldown' not in runtime.errors


def test_api_cooldown_survives_missing_faces_and_camera_offline(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    runtime, image, capture=runtime_fixture(tmp_path)
    token=runtime.face_gate.reserve(runtime.face_gate.generation)
    runtime.face_gate.bind(token,'gate-1')
    runtime.face_state={'frame_id':1,'captured_at':'now','faces':[successful_face()]}
    runtime.camera.invalidate('offline')
    client=TestClient(create_app(runtime.settings,runtime))
    live=client.get('/api/vision/live').json()
    assert live['face_cooldown']['active'] and live['face_cooldown']['command_id']=='gate-1'
    assert live['faces']==[]


def test_two_concurrent_grants_reserve_only_one_gate_command(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    runtime,image,capture=runtime_fixture(tmp_path)
    barrier=threading.Barrier(2)
    def analyze(frame,live):
        barrier.wait(timeout=2)
        return [successful_face()]
    runtime.face.analyze=analyze
    calls=[]
    def send(*args,**kwargs):
        calls.append(args)
        return {'command_id':'gate-1','status':'pending'}
    runtime.send_command=send
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(runtime.process_faces,image,i,'now',True,**capture) for i in (1,2)]
        for future in futures:future.result(timeout=3)
    assert len(calls)==1 and runtime.face_gate.snapshot()['active']


def test_real_gateway_batch_open_ack_close_and_ack_open_close_both_unlock(monkeypatch):
    from test_gateway_bridge import gateway, batch, enqueue
    from test_gateway_protocol import uno1_state
    for ack_first in (False, True):
        bridge, runtime, clock, session, messages = gateway(monkeypatch)
        gate = FaceGateCooldown()
        original_callback = runtime.on_gateway_message
        def on_message(message):
            original_callback(message)
            if message['type'] == 'ack':
                gate.command_result(message['command_id'], message['status'])
            elif message.get('device_id') == 'front_door':
                gate.observe(message['state']['position'])
        runtime.on_gateway_message = on_message
        bridge.on_dispatched = gate.dispatched
        bridge.exchange(batch(session, 0))
        token = gate.reserve(gate.generation)
        cid = enqueue(bridge)
        gate.bind(token, cid)
        clock.now += .1
        delivered = bridge.exchange(batch(session, 1))
        assert delivered['commands'][0]['command_id'] == cid
        ack = {'board':'UNO1','type':'ack','command_id':cid,'status':'acked'}
        opening = uno1_state(entrance='open')
        closing = uno1_state(entrance='closed')
        ordered = [ack, opening, closing] if ack_first else [opening, ack, closing]
        clock.now += .1
        bridge.exchange(batch(session, 2, [{'board_id':'uno1','connected':True,'messages':ordered}]))
        assert not gate.snapshot()['active'], 'completed door cycle must unlock independent of ACK order'
