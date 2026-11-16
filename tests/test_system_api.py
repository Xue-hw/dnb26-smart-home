from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.repository import RepositoryUnavailable
from backend.runtime import Runtime


def client_for(tmp_path, token='test-admin'):
    settings = Settings(data_dir=tmp_path,api_token=token,camera_enabled=False)
    runtime = Runtime(settings)
    return TestClient(create_app(settings,runtime)),runtime


def test_admin_token_protects_writes_and_old_simulation_routes(tmp_path):
    client,rt = client_for(tmp_path)
    assert client.get('/api/auth/status').json()['write_access'] is False
    assert client.get('/api/auth/status',headers={'Authorization':'Bearer test-admin'}).json()['write_access'] is True
    assert client.post('/api/devices/main_light/commands',json={'action':'set','params':{'power':True}}).status_code==401
    assert client.put('/api/settings',json={'bulb_linkage':False}).status_code==401
    assert client.post('/control',json={'target':'door','action':'open'}).status_code==410


def test_camera_offline_never_returns_old_granted_face(tmp_path):
    client,rt = client_for(tmp_path)
    rt.face_state = {'frame_id':12,'captured_at':'2026-11-16T00:00:00Z','faces':[{'access_granted':True}]}
    rt.camera.status = 'offline'
    result = client.get('/api/vision/live').json()
    assert result['faces']==[]
    assert client.get('/api/camera/stream').status_code==503
    assert client.get('/api/camera/snapshot').status_code==503


def test_database_failure_is_503_not_an_empty_success(tmp_path):
    client,rt = client_for(tmp_path)
    def fail():
        raise RepositoryUnavailable('数据库不可用')
    rt.repository.list_people = fail
    response = client.get('/api/person/list')
    assert response.status_code==503
    assert response.json()['code']=='DATABASE_UNAVAILABLE'


def test_upload_cannot_claim_live_source_or_execute_control(tmp_path):
    client,rt = client_for(tmp_path)
    rt.face.analyze = lambda image,live=False:[{
        'matched':True,'identity_matched':True,'user_id':'u1','user_name':'one','similarity':.8,
        'bbox':[1,1,5,5],'access_granted':False,'liveness_status':'unavailable','reason':'static'}]
    rt.save_image = lambda image,folder='captures':'/uploads/captures/photo.jpg'
    rt.repository.event = lambda category,payload:{**payload,'event_id':'e1'}
    rt.send_command = lambda *a,**k:pytest.fail('A photograph must never send a hardware command')
    from PIL import Image
    import io
    content = io.BytesIO()
    Image.new('RGB',(16,16)).save(content,format='JPEG')
    response = client.post('/api/face-verify',files={'image':('photo.jpg',content.getvalue(),'image/jpeg')},data={'source':'camera'})
    assert response.status_code==200
    result = response.json()
    assert result['identity_matched'] and not result['access_granted']
    assert result['source']=='upload'


@pytest.mark.parametrize('kind,action,params',[
    ('door','set',{'position':'unknown'}),('light','set',{'brightness':101}),
    ('fan','set',{'power':'true'}),('light','set',{}),('fan','on',{'power':True}),
])
def test_invalid_commands_rejected(kind,action,params):
    with pytest.raises(ValueError):
        Runtime.validate_command(kind,action,params)


def test_replay_source_is_never_live(tmp_path):
    from backend.vision.camera_service import CameraService
    assert CameraService(Settings(camera_source='sample.mp4'),lambda *a:None).replay
    assert not CameraService(Settings(camera_source='0'),lambda *a:None).replay


def test_settings_reject_bad_hysteresis_before_database_write(tmp_path):
    _,rt = client_for(tmp_path)
    with pytest.raises(ValueError):
        rt.update_options({'temperature_on':20,'temperature_off':25})
