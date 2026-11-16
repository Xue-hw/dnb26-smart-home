from contextlib import contextmanager
from datetime import datetime
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.repository import Repository
from backend.runtime import Runtime
from backend.hardware.uno_protocol import normalize_message


class CommandSQL:
    """Exercise real repository command serialization without a MySQL server."""
    def __init__(self):
        self.rows = {}
        self.selected = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self

    def execute(self, sql, args):
        if sql.startswith('INSERT INTO dnb_commands'):
            cid, key, device, payload, status, source = args
            self.rows[cid] = dict(command_id=cid, idempotency_key=key,
                device_id=device, payload_json=payload, status=status, source=source,
                requested_at=datetime(2026,11,16), acked_at=None, error_message=None)
        elif 'WHERE idempotency_key=' in sql:
            self.selected = next((r for r in self.rows.values() if r['idempotency_key']==args[0]), None)
        elif sql.startswith('UPDATE dnb_commands'):
            status,error,_,cid = args
            self.rows[cid].update(status=status,error_message=error)
        else:
            self.selected = self.rows.get(args[0])

    def fetchone(self):
        return dict(self.selected) if self.selected else None


def pin_runtime(tmp_path):
    config = Settings(data_dir=tmp_path, hardware_mode='gateway', api_token='admin')
    repo = Repository(config)
    sql = CommandSQL()
    @contextmanager
    def connection():
        yield sql
    repo.connection = connection
    runtime = Runtime(config, repo)
    sent = []
    runtime.gateway.send = lambda command, **kwargs: sent.append(command)
    return runtime, sql, sent


def test_pin_never_enters_database_public_response_sse_or_device_state(tmp_path):
    runtime, sql, sent = pin_runtime(tmp_path)
    events = runtime.events.subscribe()
    client = TestClient(create_app(runtime.settings,runtime))
    body = {'action':'set','params':{'pin':'6512'}}
    endpoint = '/api/devices/front_door/commands'
    assert client.post(endpoint,json=body).status_code == 401
    response = client.post(endpoint,json=body,headers={'Authorization':'Bearer admin'})
    assert response.status_code == 200
    command = response.json()
    assert command['params'] == {'pin':'[redacted]'}
    assert sent[0]['params'] == {'pin':'6512'}
    assert '"6512"' not in json.dumps(sql.rows,default=str)
    assert '_sensitive_fingerprint' not in json.dumps(command)
    assert '"6512"' not in json.dumps(events.get_nowait())
    assert client.get('/api/commands/'+command['command_id']).json() == command
    # No device update method is installed: a PIN request must not fabricate state.


def test_pin_retry_is_equal_only_within_process_and_never_reexecutes(tmp_path):
    runtime, sql, sent = pin_runtime(tmp_path)
    first = runtime.send_command('garage_door','set',{'pin':'0246'},'pin-retry')
    retry = runtime.send_command('garage_door','set',{'pin':'0246'},'pin-retry')
    assert first['command_id']==retry['command_id'] and len(sent)==1
    with pytest.raises(ValueError,match='幂等键'):
        runtime.send_command('garage_door','set',{'pin':'0247'},'pin-retry')
    restarted = Runtime(runtime.settings,runtime.repository)
    with pytest.raises(ValueError,match='幂等键'):
        restarted.send_command('garage_door','set',{'pin':'0246'},'pin-retry')
    assert len(sql.rows)==1 and '"0246"' not in json.dumps(sql.rows,default=str)


def test_pin_transport_failure_cannot_echo_secret_in_error(tmp_path):
    runtime, sql, _ = pin_runtime(tmp_path)
    def broken(command, **kwargs):
        raise RuntimeError('secret transport echo '+command['params']['pin'])
    runtime.gateway.send = broken
    result = runtime.send_command('front_door','set',{'pin':'7891'})
    assert result['status']=='failed'
    assert '7891' not in json.dumps([result['error_message'],[r['error_message'] for r in sql.rows.values()]])


@pytest.mark.parametrize('kind,params', [
    ('fan',{'speed':True}),('fan',{'speed':90,'power':True}),
    ('light',{'led_count':0}),('light',{'color':'#01234Z'}),
    ('door',{'pin':'1234','position':'open'}),('door',{'pin':1234}),
])
def test_runtime_rejects_invalid_extensions_before_persisting(kind,params):
    with pytest.raises(ValueError):
        Runtime.validate_command(kind,'set',params,allow_mode=True)


def test_gateway_combined_telemetry_accepts_extensions_but_never_pin(tmp_path):
    writes = []
    runtime = Runtime(Settings(data_dir=tmp_path,hardware_mode='gateway'),
        SimpleNamespace(update_device=lambda *args:writes.append(args),event=lambda *args:{}))
    state = {'power':True,'brightness':60,'color':'#123456','led_count':8,'mode':'auto'}
    runtime.ingest_telemetry({'device_id':'main_light','state':state},'gateway')
    assert writes[0][3] == state
    runtime.ingest_telemetry({'device_id':'exhaust_fan',
        'state':{'power':True,'mode':'manual','speed':70}},'gateway')
    with pytest.raises(ValueError,match='密码'):
        runtime.ingest_telemetry({'device_id':'front_door','state':{'pin':'1234'}},'gateway')


@pytest.mark.parametrize('status,rfid_ok,restricted,expected', [
    ('online',False,True,(True,False)),
    ('online',True,False,(False,False)),
    ('online',True,True,(False,False)),
    ('offline',False,False,(False,False)),
])
def test_rfid_fault_and_security_alerts_require_current_online_board(tmp_path,status,rfid_ok,restricted,expected):
    alerts = {}
    runtime = Runtime(Settings(data_dir=tmp_path,hardware_mode='gateway'),
        SimpleNamespace(alert=lambda code,message,**kwargs:alerts.update({code:kwargs['active']})))
    runtime.gateway.details = lambda:{'uno1':{'status':'online','dht_ok':True},
        'uno2':{'status':status,'rfid_ok':rfid_ok,'rfid_restricted':restricted}}
    runtime.check_gateway_alerts()
    assert (alerts['sensor.rfid.failed'],alerts['security.rfid.unrestricted']) == expected


@pytest.mark.parametrize('event,field,value', [
    ('rfid_granted','uid','04a1b2c3'),
    ('rfid_denied','uid','04A1B2C3D4E5F6'),
    ('rfid_granted','uid','0102030405060708090A'),
    ('voice','command',3),
])
def test_local_event_metadata_reaches_history_with_correct_device(tmp_path,event,field,value):
    board = 'uno1' if event=='voice' else 'uno2'
    message = normalize_message(board,{'type':'event','board':board.upper(),
        'event':event,field:value})[0]
    stored = []
    def record(*args):
        stored.append(args)
        return args[1]
    runtime = Runtime(Settings(data_dir=tmp_path,hardware_mode='gateway'),SimpleNamespace(event=record))
    runtime.on_gateway_message(message)
    payload = stored[0][1]
    if field == 'uid':
        assert 'uid' not in payload
    else:
        assert payload[field] == value
    assert payload['device_id'] == ('main_light' if event=='voice' else 'garage_door')


@pytest.mark.parametrize('board,event,fields', [
    ('uno1','voice',{'command':7}),
    ('uno1','voice',{'command':True}),
    ('uno1','voice',{'uid':'01020304'}),
    ('uno1','keypad_granted',{'command':1}),
    ('uno2','rfid_granted',{'command':1}),
    ('uno2','rfid_denied',{'uid':'01:02:03:04'}),
    ('uno2','rfid_denied',{'uid':'0102030405'}),
    ('uno2','rfid_denied',{'uid':'0102030Z'}),
])
def test_local_metadata_rejects_wrong_event_invalid_uid_or_voice_command(board,event,fields):
    with pytest.raises(ValueError):
        normalize_message(board,{'type':'event','board':board.upper(),'event':event,**fields})


def test_rfid_read_failure_event_keeps_uid_absent():
    result = normalize_message('uno2',{'type':'event','board':'UNO2','event':'rfid_denied'})[0]
    assert 'uid' not in result
