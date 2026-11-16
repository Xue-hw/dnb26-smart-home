"""Regression coverage for capture provenance, revoked users and notification races."""
import builtins
from datetime import datetime, timedelta, timezone
import queue
import time
from types import SimpleNamespace

import numpy as np
import pytest

from backend.config import Settings
from backend.runtime import EventBus, Runtime
from backend.vision.camera_service import CameraService
from backend.vision.face_service import FaceService


def live_runtime(tmp_path):
    runtime = Runtime(Settings(data_dir=tmp_path,hardware_mode='serial'))
    camera = runtime.camera
    camera.frame = np.zeros((16,16,3),dtype=np.uint8)
    camera.status = 'online'
    camera.last_frame = time.monotonic()
    runtime.record_live_event = lambda *args:None
    runtime.repository.is_authorized = lambda identity:True
    return runtime, {'captured_monotonic':camera.last_frame,'generation':camera.generation}


def grant():
    return {'new_grant':True,'user_id':'u1','reason':'blink passed',
            'access_granted':True,'liveness_status':'passed'}


def test_startup_never_restores_disabled_photo_users(tmp_path):
    photos = tmp_path/'photos'
    photos.mkdir()
    (photos/'revoked.jpg').write_bytes(b'existing delivery photo')
    runtime = Runtime(Settings(data_dir=tmp_path,bootstrap_faces_dir=photos))
    def list_people(*,include_inactive=False):
        return [{'name':'revoked','user_id':'revoked'}] if include_inactive else []
    runtime.repository.list_people = list_people
    runtime.register_person = lambda *args:pytest.fail('Startup restored revoked access')
    runtime.bootstrap_people()


def test_watchdog_invalidates_stalled_capture_and_old_provenance(tmp_path):
    runtime, capture = live_runtime(tmp_path)
    runtime.camera.last_frame -= 10
    runtime.camera.jpeg = b'old jpeg'
    runtime.camera.refresh_health()
    assert runtime.camera.status == 'offline'
    assert runtime.camera.frame is None and runtime.camera.jpeg is None
    # A reconnect may be fresh, but it must not make pre-disconnect results trusted.
    runtime.camera.status = 'online'
    runtime.camera.frame = np.zeros((16,16,3),dtype=np.uint8)
    runtime.camera.last_frame = time.monotonic()
    assert not runtime.camera.is_current_capture(**capture)


@pytest.mark.parametrize('failure',['stale','missing_provenance','disconnect_during_inference','reconnect_during_inference'])
def test_untrusted_face_results_never_dispatch_gate(tmp_path,failure):
    runtime,capture = live_runtime(tmp_path)
    def analyze(image,*,live):
        if failure in ('disconnect_during_inference','reconnect_during_inference'):
            runtime.camera.invalidate('disconnected')
            if failure=='reconnect_during_inference':
                runtime.camera.status='online'
                runtime.camera.frame=image
                runtime.camera.last_frame=time.monotonic()
        return [grant()]
    runtime.face.analyze = analyze
    runtime.send_command = lambda *args,**kwargs:pytest.fail('Untrusted sample attempted open')
    if failure=='stale':
        capture['captured_monotonic']-=30
    if failure=='missing_provenance':
        capture={}
    runtime.process_faces(np.zeros((16,16,3),dtype=np.uint8),1,'2026-11-16T00:00:00Z',True,**capture)
    assert runtime.face_state['faces']==[]


def test_command_creation_cannot_outlive_the_capture_session(tmp_path):
    runtime,capture = live_runtime(tmp_path)
    command={'command_id':'c1','status':'pending'}
    def create(*args):
        runtime.camera.invalidate('disconnected while MySQL was processing')
        return command,True
    runtime.repository.create_command=create
    runtime.repository.finish_command=lambda cid,status,error=None:{**command,'status':status,'error_message':error}
    runtime.serial.send=lambda *args:pytest.fail('Stale gate command reached Arduino')
    result=runtime.send_command('front_door','set',{'position':'open'},source='face',
                                capture=(capture['captured_monotonic'],capture['generation']))
    assert result['status']=='failed'


def test_current_blink_dispatches_once_and_keeps_receipt_in_subsequent_frames(tmp_path):
    runtime,capture=live_runtime(tmp_path)
    runtime.settings.hardware_mode='mock'
    session=runtime.face.session
    ears=iter([.3,.1,.1,.3,.3,.3])
    runtime.face.analyze=lambda image,live:[session.observe('u1',next(ears),live=live)]
    created=[]
    command={'command_id':'gate-1','status':'pending'}
    def create(*args):
        created.append(args)
        return command,True
    runtime.repository.create_command=create
    runtime.repository.devices=lambda:[]
    runtime.repository.update_device=lambda *args:None
    runtime.repository.finish_command=lambda cid,status,error=None:{**command,'status':status}
    runtime.repository.event=lambda category,payload,device_id=None:payload
    image=np.zeros((16,16,3),dtype=np.uint8)
    for frame_id in range(6):
        runtime.process_faces(image,frame_id,'2026-11-16T00:00:00Z',True,**capture)
    assert len(created)==1
    face=runtime.face_state['faces'][0]
    assert face['access_granted']
    assert face['command_id']=='gate-1'


def test_disconnect_during_yolo_never_triggers_bulb_linkage(tmp_path):
    runtime,capture = live_runtime(tmp_path)
    runtime.last_recognition=time.monotonic()
    runtime.bulb_count=2
    def detect(frame):
        runtime.camera.invalidate('camera disconnected during inference')
        return [{'label':'light_bulb','confidence':.9,'bbox':[0,0,8,8]}],1.
    runtime.models.detect=detect
    runtime.send_command=lambda *args,**kwargs:pytest.fail('Stale bulb result triggered hardware')
    runtime.process_frame(np.zeros((16,16,3),dtype=np.uint8),1,'2026-11-16T00:00:00Z',True,**capture)
    assert runtime.bulb_count==0


def test_concurrent_sse_drain_does_not_fail_an_executed_command():
    class DrainingQueue(queue.Queue):
        def put_nowait(self,item):
            if self.full():
                while not self.empty():
                    self.get_nowait()
                raise queue.Full
            return super().put_nowait(item)
    target=DrainingQueue(maxsize=1)
    target.put_nowait({'type':'old'})
    bus=EventBus()
    bus.subscribers.add(target)
    bus.publish('command.updated',{'status':'acked'})
    assert target.get_nowait()['payload']['status']=='acked'


def test_face_command_receipt_survives_following_frames_and_resets(tmp_path):
    service=FaceService(Settings(data_dir=tmp_path),SimpleNamespace())
    session=service.session
    session.observe('u1',.3,now=1)
    session.observe('u1',.1,now=1.1)
    session.observe('u1',.1,now=1.2)
    assert session.observe('u1',.3,now=1.3)['new_grant']
    service.remember_command('u1','gate-1')
    assert session.observe('u1',.3,now=1.4)['command_id']=='gate-1'
    assert session.observe('u1',.3,now=1.5,live=False)['access_granted'] is False
    assert session.observe('u1',.3,now=1.6)['command_id']=='gate-1'
    assert session.observe('u2',.3,now=1.7)['command_id'] is None


def test_face_dependency_systemexit_marks_service_offline(tmp_path,monkeypatch):
    original=builtins.__import__
    def broken_import(name,*args,**kwargs):
        if name=='face_recognition':
            raise SystemExit('missing native dependency')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',broken_import)
    service=FaceService(Settings(data_dir=tmp_path),SimpleNamespace())
    service.initialize()
    assert service.status=='offline'
    assert 'missing native dependency' in service.message


def test_periodic_open_telemetry_does_not_reset_door_alarm_clock(tmp_path):
    runtime=Runtime(Settings(data_dir=tmp_path))
    now=datetime.now(timezone.utc)
    device={'device_id':'front_door','kind':'door','state':{'position':'open'},
            'open_since':(now-timedelta(minutes=2)).isoformat(),'updated_at':now.isoformat()}
    runtime.repository.devices=lambda:[device]
    alerts=[]
    runtime.repository.alert=lambda code,message,active:alerts.append(active)
    runtime.check_door_alerts()
    assert alerts==[True]
    device['state']['position']='closed'
    runtime.check_door_alerts()
    assert alerts==[True,False]
