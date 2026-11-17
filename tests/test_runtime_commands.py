from copy import deepcopy
import pytest

from backend.config import Settings
from backend.runtime import Runtime


class CommandRepository:
    """Test-only persistence double; production always uses MySQL."""
    def __init__(self):
        self.commands = {}
        self.keys = {}
        self.writes = 0
        self.state = {'power':False,'brightness':0}

    def create_command(self,device_id,payload,source,key=None):
        if key in self.keys:
            old = self.commands[self.keys[key]]
            if old['params']!=payload['params'] or old['action']!=payload['action']:
                raise ValueError('幂等键已被使用')
            return deepcopy(old),False
        command = {**deepcopy(payload),'command_id':str(len(self.commands)+1),'status':'pending','source':source}
        self.commands[command['command_id']] = command
        if key:
            self.keys[key] = command['command_id']
        return deepcopy(command),True

    def devices(self):
        return [{'device_id':'main_light','state':deepcopy(self.state)}]

    def update_device(self,device_id,name,kind,state,source):
        self.writes += 1
        self.state = deepcopy(state)

    def finish_command(self,command_id,status,error=None):
        self.commands[command_id].update(status=status,error_message=error)
        return deepcopy(self.commands[command_id])

    def event(self,category,payload,device_id=None):
        return payload


def test_idempotency_key_does_not_repeat_device_execution(tmp_path):
    repo = CommandRepository()
    runtime = Runtime(Settings(data_dir=tmp_path,hardware_mode='mock'),repo)
    first = runtime.send_command('main_light','toggle',{},'retry-1')
    second = runtime.send_command('main_light','toggle',{},'retry-1')
    assert first['command_id']==second['command_id']
    assert repo.writes==1
    assert repo.state['power'] is True
    assert first['source']=='mock'


def test_same_key_cannot_execute_different_action(tmp_path):
    repo = CommandRepository()
    runtime = Runtime(Settings(data_dir=tmp_path),repo)
    runtime.send_command('main_light','set',{'power':True},'same')
    with pytest.raises(ValueError):
        runtime.send_command('main_light','set',{'power':False},'same')
    assert repo.writes==1


def test_serial_offline_command_fails_without_fabricating_state(tmp_path):
    repo = CommandRepository()
    runtime = Runtime(Settings(data_dir=tmp_path,hardware_mode='serial'),repo)
    result = runtime.send_command('main_light','set',{'power':True})
    assert result['status']=='failed'
    assert repo.writes==0
    assert not repo.state['power']


def test_replay_frames_never_send_open_command(tmp_path):
    import numpy as np
    runtime = Runtime(Settings(data_dir=tmp_path,camera_source='recording.mp4'),CommandRepository())
    def analyze(image,*,live):
        assert not live
        return [{'new_grant':False,'access_granted':False,'identity_matched':True}]
    runtime.face.analyze = analyze
    runtime.send_command = lambda *a,**k:pytest.fail('replay attempted hardware command')
    runtime.process_faces(np.zeros((16,16,3),dtype=np.uint8),1,'2026-11-16T00:00:00Z',False)
    assert not runtime.face_state['faces'][0]['access_granted']
