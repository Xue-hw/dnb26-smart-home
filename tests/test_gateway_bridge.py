from copy import deepcopy
from types import SimpleNamespace
import uuid

import pytest

from backend.hardware.gateway_bridge import GatewayBridge
from test_gateway_protocol import uno1_state, uno2_state


class GatewayRepository:
    def __init__(self):
        self.commands = {}

    def command(self, command_id):
        return deepcopy(self.commands[command_id])

    def finish_command(self, command_id, status, reason=None):
        item = self.commands[command_id]
        if item['status'] == 'pending':
            item.update(status=status, error_message=reason)
        return deepcopy(item)


def gateway(monkeypatch):
    clock = SimpleNamespace(now=100.)
    monkeypatch.setattr('backend.hardware.gateway_bridge.time.monotonic', lambda: clock.now)
    repo = GatewayRepository()
    messages = []
    camera = SimpleNamespace(ACTION_FRAME_MAX_AGE=1.5, valid=True)
    camera.is_current_capture = lambda *capture: camera.valid
    def on_message(message):
        messages.append(message)
        if message['type'] == 'ack':
            repo.finish_command(message['command_id'], message['status'])
    runtime = SimpleNamespace(repository=repo, camera=camera, on_gateway_message=on_message,
        options={'temperature_on': 30, 'temperature_off': 28},
        events=SimpleNamespace(publish=lambda *args: None))
    service = GatewayBridge(runtime)
    session = str(uuid.uuid4())
    return service, runtime, clock, session, messages


def batch(session, sequence, boards=None):
    return {'session_id': session, 'exchange_id': sequence, 'boards': boards if boards is not None else [
        {'board_id': 'uno1', 'connected': True, 'messages': [uno1_state()]},
        {'board_id': 'uno2', 'connected': True, 'messages': [uno2_state()]}]}


def enqueue(service, device='front_door', capture=None):
    command = {'command_id': uuid.uuid4().hex, 'device_id': device, 'action': 'set',
               'params': {'position': 'open'} if device in ('front_door', 'garage_door') else {'power': True},
               'status': 'pending'}
    service.runtime.repository.commands[command['command_id']] = command
    service.send(command, capture=capture)
    return command['command_id']


def test_commands_are_consumed_once_and_ack_is_bound_to_target_board(monkeypatch):
    service, runtime, clock, session, messages = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    cid = enqueue(service)
    reply = service.exchange(batch(session, 1))
    assert reply['commands'][0]['command_id'] == cid
    assert reply['settings']['config_sync'] is True
    assert service.exchange(batch(session, 2))['commands'] == []
    wrong = {'board': 'UNO2', 'type': 'ack', 'command_id': cid, 'status': 'acked'}
    service.exchange(batch(session, 3, [{'board_id': 'uno2', 'connected': True, 'messages': [wrong]}]))
    assert runtime.repository.command(cid)['status'] == 'pending'
    correct = {**wrong, 'board': 'UNO1'}
    service.exchange(batch(session, 4, [{'board_id': 'uno1', 'connected': True, 'messages': [correct]}]))
    assert runtime.repository.command(cid)['status'] == 'acked'


def test_two_clients_color_and_count_changes_preserve_each_other_without_new_telemetry(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    for params in ({'color': '#0000FF'}, {'led_count': 4}):
        cid = uuid.uuid4().hex
        command = {'command_id': cid, 'device_id': 'main_light', 'action': 'set',
                   'params': params, 'status': 'pending'}
        runtime.repository.commands[cid] = command
        service.send(command)
    commands = service.exchange(batch(session, 1))['commands']
    assert [(c['opcode'], c['args']) for c in commands] == [('LAMP_COLOR', [0, 0, 255])]
    assert len(service.pending) == 1
    ack = {'board': 'UNO1', 'type': 'ack', 'command_id': commands[0]['command_id'], 'status': 'acked'}
    # ACK alone cannot bypass UART pacing; the second operation stays queued.
    assert service.exchange(batch(session, 2, [{'board_id':'uno1','connected':True,'messages':[ack]}]))['commands'] == []
    clock.now += 1.2
    second = service.exchange(batch(session, 3))['commands']
    assert [(c['opcode'], c['args']) for c in second] == [('LAMP_COUNT', [4])]
    assert not service.pending


@pytest.mark.parametrize('failure', ['expired', 'camera_changed', 'network_gap', 'new_session', 'usb_disconnect'])
def test_delayed_or_reconnected_open_command_is_never_replayed(monkeypatch, failure):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    cid = enqueue(service, capture=(clock.now, 1))
    if failure == 'expired':
        clock.now += 2
    elif failure == 'camera_changed':
        runtime.camera.valid = False
    elif failure == 'network_gap':
        clock.now += 11
    elif failure == 'new_session':
        session = str(uuid.uuid4())
    boards = [{'board_id': 'uno1', 'connected': False, 'messages': []}] if failure == 'usb_disconnect' else None
    assert service.exchange(batch(session, 1, boards))['commands'] == []
    assert runtime.repository.command(cid)['status'] == 'failed'


def test_one_disconnected_board_does_not_disable_the_other_board(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    service.exchange(batch(session, 1, [{'board_id': 'uno2', 'connected': False, 'messages': []}]))
    assert not service.online
    assert service.board_online('uno1')
    assert not service.board_online('uno2')
    cid = enqueue(service, device='main_light')
    assert service.exchange(batch(session, 2))['commands'][0]['command_id'] == cid


def test_late_ack_cannot_turn_a_timeout_into_success(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    cid = enqueue(service)
    service.exchange(batch(session, 1))
    runtime.repository.finish_command(cid, 'timeout')
    ack = {'board': 'UNO1', 'type': 'ack', 'command_id': cid, 'status': 'acked'}
    service.exchange(batch(session, 2, [{'board_id': 'uno1', 'connected': True, 'messages': [ack]}]))
    assert runtime.repository.command(cid)['status'] == 'timeout'


def test_duplicate_sequence_and_retired_session_are_rejected(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    with pytest.raises(ValueError):
        service.exchange(batch(session, 0))
    service.exchange(batch(str(uuid.uuid4()), 0))
    with pytest.raises(RuntimeError):
        service.exchange(batch(session, 1))


def test_state_frames_are_required_for_online_not_just_pc_connected(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0, [{'board_id': 'uno1', 'connected': True, 'messages': [
        {'board': 'UNO1', 'type': 'identity', 'protocol': 1}]}]))
    assert not service.board_online('uno1')
    with pytest.raises(RuntimeError):
        enqueue(service)


def test_stale_message_batch_is_rejected_before_any_state_side_effects(monkeypatch):
    service, runtime, clock, session, messages = gateway(monkeypatch)
    payload = batch(session, 0)
    payload['boards'][1]['age_ms'] = 2500
    with pytest.raises(ValueError):
        service.exchange(payload)
    assert messages == [] and service.session_id is None


def test_dht_failure_marks_only_temperature_humidity_invalid(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    payload = batch(session, 0)
    payload['boards'][0]['messages'] = [uno1_state(dht_ok=False, temperature=None, humidity=None)]
    service.exchange(payload)
    assert service.sensor_valid('light')
    assert not service.sensor_valid('temperature') and not service.sensor_valid('humidity')


def test_usb_reconnect_requires_fresh_state_even_with_same_pc_session(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    service.exchange(batch(session, 1, [{'board_id': 'uno1', 'connected': False, 'messages': []}]))
    service.exchange(batch(session, 2, [{'board_id': 'uno1', 'connected': True, 'messages': [
        {'type': 'identity', 'board': 'UNO1', 'protocol': 1}]}]))
    assert not service.board_online('uno1')
    assert 'front_door' not in service.states


def test_serial_connection_id_change_cancels_commands_even_without_offline_batch(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    payload = batch(session, 0)
    payload['boards'][0]['connection_id'] = 'first-open'
    service.exchange(payload)
    cid = enqueue(service)
    payload = batch(session, 1)
    payload['boards'][0]['connection_id'] = 'second-open'
    assert service.exchange(payload)['commands'] == []
    assert runtime.repository.command(cid)['status'] == 'failed'


def test_temperature_sync_status_uses_reported_values_not_save_or_ack(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    assert not service.details()['uno1']['temperature_config_synced']
    payload = batch(session, 1)
    payload['boards'][0]['messages'] = [uno1_state(temperature_on=30., temperature_off=28.)]
    service.exchange(payload)
    assert service.details()['uno1']['temperature_config_synced']
    clock.now += 11
    assert not service.details()['uno1']['temperature_config_synced']


def test_same_board_queue_expires_without_replaying_or_blocking_other_board(monkeypatch):
    service, runtime, clock, session, _ = gateway(monkeypatch)
    service.exchange(batch(session, 0))
    first = enqueue(service)
    queued = enqueue(service, device='main_light')
    garage = enqueue(service, device='garage_door')
    commands = service.exchange(batch(session, 1))['commands']
    assert {c['command_id'] for c in commands} == {first, garage}
    assert queued in service.pending
    clock.now += 5.1
    assert not service.exchange(batch(session, 2))['commands']
    assert runtime.repository.command(queued)['status'] == 'failed'
