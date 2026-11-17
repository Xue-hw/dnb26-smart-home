import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.runtime import Runtime


def person_runtime(tmp_path):
    settings=Settings(data_dir=tmp_path,camera_enabled=False)
    runtime=Runtime(settings)
    feature=tmp_path/'feature.npy'
    encoding=np.zeros(128)
    np.save(feature,encoding)
    person={'user_id':'test-1','name':'test','feature_version':'v1','face_feature_path':str(feature)}
    runtime.repository.list_people=lambda **kwargs:[dict(person)]
    runtime.face.status='online'
    runtime.face.people=[(dict(person),encoding)]
    runtime.send_command=lambda *args,**kwargs:pytest.fail('Enrollment confirmation must be read-only')
    return runtime,feature


def test_enrollment_confirmation_requires_valid_feature_and_loaded_identity(tmp_path):
    runtime,_=person_runtime(tmp_path)
    client=TestClient(create_app(runtime.settings,runtime))
    response=client.get('/api/person/enrollment',params={'user_id':'test-1'})
    assert response.status_code==200
    result=response.json()
    assert result['status']=='ready' and result['active'] and result['loaded']
    assert 'face_feature_path' not in str(result) and str(tmp_path) not in str(result)
    assert 'encoding' not in result


@pytest.mark.parametrize('condition,expected',[
    ('missing','feature_missing'),('invalid','feature_invalid'),('offline','model_unavailable'),
    ('unloaded','not_loaded'),('stale','not_loaded'),('inactive','inactive'),('absent','not_found'),
])
def test_enrollment_confirmation_reports_specific_backend_failure(tmp_path,condition,expected):
    runtime,feature=person_runtime(tmp_path)
    if condition=='missing': feature.unlink()
    if condition=='invalid': np.save(feature,np.zeros(5))
    if condition=='offline': runtime.face.status='offline'
    if condition=='unloaded': runtime.face.people=[]
    if condition=='stale': np.save(feature,np.ones(128))
    if condition=='inactive':
        original=runtime.repository.list_people
        runtime.repository.list_people=lambda **kwargs:original() if kwargs.get('include_inactive') else []
    if condition=='absent': runtime.repository.list_people=lambda **kwargs:[]
    assert runtime.person_enrollment('test-1')['status']==expected
