from types import SimpleNamespace
import threading
import uuid

import httpx
import pytest

from integrations.hardware.gateway.client import BoardLink, LineFramer, exchange_once


def active_link(monkeypatch):
    now = SimpleNamespace(value=100.)
    monkeypatch.setattr('integrations.hardware.gateway.client.time.monotonic', lambda: now.value)
    link = BoardLink('uno1', 'COM_TEST', threading.Event())
    writes = []
    link.connection = SimpleNamespace(write=lambda raw: writes.append(raw) or len(raw))
    link.identified = True
    link.last_state = now.value
    return link, now, writes


def wire(ttl=1000):
    return {'board_id': 'uno1', 'command_id': uuid.uuid4().hex,
            'opcode': 'DOOR_OPEN', 'args': [], 'ttl_ms': ttl}


def test_slow_serial_lines_survive_fragmented_reads_and_mixed_diagnostics():
    framer = LineFramer()
    assert framer.feed(b'log\r\nDNB1 {"type":') == [b'log']
    assert framer.feed(b'"state"}\r') == []
    assert framer.feed(b'\n') == [b'DNB1 {"type":"state"}']


def test_oversized_line_is_discarded_through_newline_without_truncated_command():
    framer = LineFramer()
    assert framer.feed(b'x'*2200) == []
    assert framer.feed(b'DNB1 dangerous\nID\n') == [b'ID']


def test_identity_is_checked_before_state_can_make_port_online(monkeypatch):
    link, now, _ = active_link(monkeypatch)
    link.identified = False
    link.accept({'board': 'UNO1', 'type': 'state'})
    assert not link.online()
    with pytest.raises(ValueError, match='身份'):
        link.accept({'board': 'UNO2', 'type': 'identity'})
    link.accept({'board': 'UNO1', 'type': 'identity', 'protocol': 1})
    link.accept({'board': 'UNO1', 'type': 'state'})
    assert link.online()
    now.value += 8.01
    assert not link.online()


def test_snapshot_drops_old_frames_and_carries_usb_connection_identity(monkeypatch):
    link, now, _ = active_link(monkeypatch)
    link.messages.append((97., {'old': True}))
    link.messages.append((99.8, {'current': True}))
    batch, generation = link.snapshot()
    assert batch['messages'] == [{'current': True}]
    assert batch['connection_id'] == link.connection_id
    assert 199 < batch['age_ms'] < 201
    assert link.snapshot()[0]['messages'] == []


def test_identity_on_an_open_usb_port_invalidates_pre_reset_state_and_commands(monkeypatch):
    link, _, writes = active_link(monkeypatch)
    old_generation, old_connection = link.generation, link.connection_id
    link.messages.append((100., {'type': 'state'}))
    link.state = {'old': True}
    link.accept({'board': 'UNO1', 'type': 'identity', 'protocol': 1})
    assert link.generation != old_generation
    assert link.connection_id != old_connection
    assert not link.online()
    assert link.state == {}
    assert not link.send(wire(), 102., old_generation)
    assert writes == []
    assert link.snapshot()[0]['messages'] == []
    link.accept({'board': 'UNO1', 'type': 'state'})
    assert link.online()


def test_usb_write_rejects_expired_commands_and_changed_connection(monkeypatch):
    link, now, writes = active_link(monkeypatch)
    command = wire()
    assert not link.send(command, 100.01, 0)
    assert not link.send(command, 101., 9)
    assert writes == []
    assert link.send(command, 101., 0)
    assert writes == [b'DNB1 '+command['command_id'].encode()+b' DOOR_OPEN\n']


def test_partial_usb_write_is_an_error_and_is_not_retried(monkeypatch):
    link, _, _ = active_link(monkeypatch)
    attempts = []
    link.connection.write = lambda raw: attempts.append(raw) or 3
    with pytest.raises(OSError, match='不完整'):
        link.send(wire(), 102., 0)
    assert len(attempts) == 1


def test_slow_http_response_consumes_command_ttl_before_write(monkeypatch):
    link, now, writes = active_link(monkeypatch)
    def response(request):
        now.value += 1.2
        return httpx.Response(200, json={'commands': [wire(1000)], 'settings': {'config_sync': False}})
    with httpx.Client(base_url='http://test', transport=httpx.MockTransport(response)) as client:
        exchange_once(client, {'uno1': link}, str(uuid.uuid4()), 1)
    assert not writes


def test_exchange_uses_sequence_and_forwards_only_current_frames(monkeypatch):
    import json
    link, now, writes = active_link(monkeypatch)
    link.messages.append((now.value, {'type': 'event', 'event': 'voice', 'board': 'UNO1'}))
    seen = []
    command = wire()
    def response(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'commands': [command] if len(seen) == 1 else [], 'settings': {}})
    session = str(uuid.uuid4())
    with httpx.Client(base_url='http://test', transport=httpx.MockTransport(response)) as client:
        exchange_once(client, {'uno1': link}, session, 1)
        exchange_once(client, {'uno1': link}, session, 2)
    assert seen[0]['session_id'] == session
    assert [batch['exchange_id'] for batch in seen] == [1, 2]
    assert seen[0]['boards'][0]['messages'][0]['event'] == 'voice'
    assert seen[1]['boards'][0]['messages'] == []
    assert len(writes) == 1


def test_disabled_temperature_sync_sends_nothing(monkeypatch):
    link, _, writes = active_link(monkeypatch)
    link.sync_settings({'config_sync': False, 'temperature_on': 30, 'temperature_off': 28}, 0)
    assert writes == []


def test_temperature_ack_is_not_state_confirmation_and_failed_sync_is_retried(monkeypatch):
    link, now, writes = active_link(monkeypatch)
    settings = {'config_sync': True, 'temperature_on': 30.1, 'temperature_off': 28}
    link.sync_settings(settings, link.generation)
    first = link.config_pending
    assert b' TEMP_LIMITS 30.1 28\n' in writes[0]
    link.accept({'board': 'UNO1', 'type': 'ack', 'command_id': first, 'status': 'failed'})
    assert link.config_pending is None
    assert 'temperature_on' not in link.state
    assert not link.messages  # Private configuration ACKs never become business ACKs.
    now.value += 4
    link.sync_settings(settings, link.generation)
    assert len(writes) == 1
    now.value += 1.1
    link.sync_settings(settings, link.generation)
    second = link.config_pending
    assert second != first and len(writes) == 2
    link.accept({'board': 'UNO1', 'type': 'ack', 'command_id': second, 'status': 'acked'})
    assert 'temperature_on' not in link.state
    link.accept({'board': 'UNO1', 'type': 'state', 'temperature_on': 30.1, 'temperature_off': 28})
    now.value += 5.1
    link.accept({'board': 'UNO1', 'type': 'state', 'temperature_on': 30.1, 'temperature_off': 28})
    link.sync_settings(settings, link.generation)
    assert len(writes) == 2


def test_configuration_cannot_cross_a_controller_reset(monkeypatch):
    link, _, writes = active_link(monkeypatch)
    generation = link.generation
    link.accept({'board': 'UNO1', 'type': 'identity', 'protocol': 1})
    link.sync_settings({'config_sync': True, 'temperature_on': 30, 'temperature_off': 28}, generation)
    assert link.config_pending is None and writes == []


def test_lost_http_response_does_not_replay_local_events_or_execute_unreceived_commands(monkeypatch):
    import json
    link, now, writes = active_link(monkeypatch)
    link.messages.append((now.value, {'board': 'UNO1', 'type': 'event', 'event': 'keypad_granted'}))
    seen = []
    def response(request):
        seen.append(json.loads(request.content))
        if len(seen) == 1:
            raise httpx.ReadTimeout('response lost', request=request)
        return httpx.Response(200, json={'commands': [], 'settings': {}})
    session = str(uuid.uuid4())
    with httpx.Client(base_url='http://test', transport=httpx.MockTransport(response)) as client:
        with pytest.raises(httpx.ReadTimeout):
            exchange_once(client, {'uno1': link}, session, 1)
        exchange_once(client, {'uno1': link}, session, 2)
    assert len(seen[0]['boards'][0]['messages']) == 1
    assert seen[1]['boards'][0]['messages'] == []
    assert writes == []


def test_pc_to_backend_response_loss_consumes_command_and_reconnect_marks_result_unknown(monkeypatch):
    import json
    from test_gateway_bridge import gateway, enqueue
    from test_gateway_protocol import uno1_state
    service, runtime, clock, session, _ = gateway(monkeypatch)
    link = BoardLink('uno1', 'COM_TEST', threading.Event())
    writes = []
    link.connection = SimpleNamespace(write=lambda raw: writes.append(raw) or len(raw))
    link.accept({'board': 'UNO1', 'type': 'identity', 'protocol': 1})
    link.accept(uno1_state(temperature_on=30, temperature_off=28))
    lose_response = False
    def response(request):
        result = service.exchange(json.loads(request.content))
        if lose_response:
            assert len(result['commands']) == 1
            raise httpx.ReadTimeout('command response lost', request=request)
        return httpx.Response(200, json=result)
    with httpx.Client(base_url='http://test', transport=httpx.MockTransport(response)) as client:
        exchange_once(client, {'uno1': link}, session, 1)
        cid = enqueue(service)
        lose_response = True
        with pytest.raises(httpx.ReadTimeout):
            exchange_once(client, {'uno1': link}, session, 2)
        lose_response = False
        exchange_once(client, {'uno1': link}, session, 3)
        assert writes == []
        assert runtime.repository.command(cid)['status'] == 'pending'
        # Controller RESET while USB-UART remains open changes connection identity.
        link.accept({'board': 'UNO1', 'type': 'identity', 'protocol': 1})
        link.accept(uno1_state(temperature_on=30, temperature_off=28))
        exchange_once(client, {'uno1': link}, session, 4)
    assert writes == []
    assert runtime.repository.command(cid)['status'] == 'timeout'
    assert '未知' in runtime.repository.command(cid)['error_message']


def test_serial_writes_are_paced_with_original_deadline(monkeypatch):
    link, clock, writes = active_link(monkeypatch)
    waits = []
    def wait(duration):
        waits.append(duration)
        clock.value += duration
        return False
    monkeypatch.setattr(link.stop, 'wait', wait)
    assert link.send(wire(), 105., link.generation)
    assert link.send(wire(), 105., link.generation)
    assert waits == pytest.approx([1.1])
    assert len(writes) == 2
    assert not link.send(wire(), clock.value+.5, link.generation)
    assert len(writes) == 2


def test_connection_change_during_pacing_cancels_without_replay(monkeypatch):
    link, clock, writes = active_link(monkeypatch)
    assert link.send(wire(), 105., link.generation)
    def wait(duration):
        clock.value += duration
        link.generation += 1
        return False
    monkeypatch.setattr(link.stop, 'wait', wait)
    assert not link.send(wire(), 105., link.generation)
    assert len(writes) == 1


def test_settings_wait_does_not_hold_serial_reader_lock(monkeypatch):
    link, clock, _ = active_link(monkeypatch)
    link.last_write = clock.value
    accepted = threading.Event()
    def wait(duration):
        worker = threading.Thread(target=lambda: (link.accept({'type':'state','board':'UNO1'}), accepted.set()))
        worker.start()
        assert accepted.wait(.5), 'reader must receive state while config write is paced'
        worker.join(.5)
        clock.value += duration
        return False
    monkeypatch.setattr(link.stop, 'wait', wait)
    link.sync_settings({'config_sync':True,'temperature_on':30,'temperature_off':28},link.generation)
    assert accepted.is_set()
