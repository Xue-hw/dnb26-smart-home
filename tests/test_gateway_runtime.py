from datetime import datetime, timezone
from types import SimpleNamespace
import time
import uuid

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.runtime import Runtime
import pytest


def test_gateway_api_requires_its_own_token_and_enabled_mode(tmp_path):
    config = Settings(data_dir=tmp_path, hardware_mode='gateway', api_token='admin',
                      gateway_token='pc-secret', allow_unauthenticated_writes=True)
    runtime = Runtime(config)
    runtime.gateway.exchange = lambda payload: {'commands': [], 'received': payload}
    client = TestClient(create_app(config, runtime))
    payload = {'session_id': str(uuid.uuid4()), 'exchange_id': 0, 'boards': []}
    assert client.post('/api/hardware/gateway/exchange', json=payload).status_code == 401
    assert client.post('/api/hardware/gateway/exchange', json=payload,
                       headers={'Authorization': 'Bearer admin'}).status_code == 401
    headers = {'Authorization': 'Bearer pc-secret'}
    assert client.post('/api/hardware/gateway/exchange', json=payload, headers=headers).status_code == 200
    assert client.post('/api/hardware/gateway/exchange', content=b'x'*32769, headers=headers).status_code == 413
    assert client.post('/api/hardware/gateway/exchange', content=b'{broken', headers=headers).status_code == 400
    config.hardware_mode = 'mock'
    assert client.post('/api/hardware/gateway/exchange', json=payload, headers=headers).status_code == 409


def test_gateway_dashboard_hides_old_simulation_and_absent_hardware(tmp_path):
    stamp = datetime.now(timezone.utc).isoformat()
    rows = [
        {'device_id': 'window_1', 'kind': 'window', 'source': 'mock', 'updated_at': stamp, 'state': {'position': 'closed'}},
        {'device_id': 'front_door', 'kind': 'door', 'source': 'gateway', 'updated_at': stamp,
         'state': {'position': 'closed', 'state_basis': 'actuator'}},
        {'device_id': 'garage_door', 'kind': 'door', 'source': 'gateway', 'updated_at': stamp,
         'state': {'position': 'moving', 'state_basis': 'actuator'}},
        {'device_id': 'thermometer_1', 'kind': 'sensor', 'source': 'gateway', 'updated_at': stamp,
         'state': {'temperature': 25, 'humidity': 45, 'light': 700, 'smoke': 0, 'rain': 0},
         'metric_measured_at': {k: stamp for k in ('temperature', 'humidity', 'light', 'smoke', 'rain')}}]
    repo = SimpleNamespace(devices=lambda: rows, events=lambda *args, **kwargs: {'items': []})
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'), repo)
    now = time.monotonic()
    runtime.gateway.last_exchange = now
    runtime.gateway.boards['uno1'].update(connected=True, last_seen=now, state={'dht_ok': False})
    dashboard = runtime.dashboard()
    assert {d['device_id'] for d in dashboard['devices']} == {'front_door', 'garage_door'}
    assert dashboard['devices'][0]['board_id'] == 'uno1'
    assert dashboard['devices'][0]['capabilities'] == ['position', 'pin']
    assert dashboard['devices'][0]['status'] == 'online'
    assert dashboard['devices'][1]['status'] == 'offline'
    sensors = {s['metric']: s for s in dashboard['sensors']}
    assert set(sensors) == {'temperature', 'humidity', 'light'}
    assert sensors['temperature']['status'] == 'offline'
    assert sensors['humidity']['status'] == 'offline'
    assert sensors['light']['status'] == 'online'


def test_gateway_telemetry_accepts_actuator_metadata_without_fabricating_sensor_state(tmp_path):
    writes, events = [], []
    repo = SimpleNamespace(update_device=lambda *args: writes.append(args),
                           event=lambda *args: events.append(args))
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'), repo)
    runtime.on_gateway_message({'type': 'telemetry', 'device_id': 'garage_door',
                               'state': {'position': 'moving', 'state_basis': 'actuator'}})
    assert writes[0][3] == {'position': 'moving', 'state_basis': 'actuator'}
    assert writes[0][4] == 'gateway'
    runtime.on_gateway_message({'type': 'local_event', 'board_id': 'uno1', 'event': 'keypad_denied'})
    assert events[-1][1]['action'] == 'keypad_denied'
    assert events[-1][1]['state'] == {}


def test_gateway_token_is_loaded_only_from_explicit_environment(monkeypatch):
    monkeypatch.setenv('DNB_GATEWAY_TOKEN', 'local-test-token')
    assert Settings.from_env().gateway_token == 'local-test-token'


def test_uno_owns_temperature_automation_even_when_report_exceeds_threshold(tmp_path):
    repo = SimpleNamespace(update_device=lambda *args: None, event=lambda *args: {},
                           alert=lambda *args, **kwargs: None)
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'), repo)
    runtime.send_command = lambda *args, **kwargs: pytest.fail('Backend took temperature control away from UNO')
    runtime.ingest_telemetry({'device_id': 'thermometer_1', 'state': {'temperature': 40}}, 'gateway')
    runtime.ingest_telemetry({'device_id': 'thermometer_1', 'state': {'temperature': 15}}, 'gateway')


def test_gateway_threshold_precision_matches_firmware_reporting(tmp_path):
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'),
                      SimpleNamespace(save_settings=lambda values: None))
    with pytest.raises(ValueError, match='1位小数'):
        runtime.update_options({'temperature_on': 30.25})
    assert runtime.update_options({'temperature_on': 30.1})['temperature_on'] == 30.1


def test_mode_commands_are_enabled_only_for_the_gateway_device_contract():
    with pytest.raises(ValueError):
        Runtime.validate_command('fan', 'set', {'mode': 'auto'})
    assert Runtime.validate_command('fan', 'set', {'mode': 'auto'}, allow_mode=True) == {'mode': 'auto'}
    assert Runtime.validate_command('light', 'set', {'mode': 'manual', 'brightness': 40}, allow_mode=True)['brightness'] == 40
    with pytest.raises(ValueError):
        Runtime.validate_command('light', 'set', {'mode': 'auto', 'power': True}, allow_mode=True)


def test_old_mock_door_cannot_create_a_physical_gateway_door_alarm(tmp_path):
    calls = []
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'),
                      SimpleNamespace(devices=lambda: [{'device_id': 'front_door', 'kind': 'door',
                          'source': 'mock', 'state': {'position': 'open'}}],
                          alert=lambda *args, **kwargs: calls.append(args)))
    runtime.check_door_alerts()
    assert calls == []
