import json
import pytest

from backend.hardware.uno_protocol import command_to_wire, encode_command, normalize_message, parse_serial_line


def uno1_state(**changes):
    return {'board': 'UNO1', 'type': 'state', 'temperature': 25., 'humidity': 45.,
        'light': 600, 'dht_ok': True, 'lamp_power': True, 'brightness': 20,
        'lamp_mode': 'auto', 'fan_power': False, 'fan_mode': 'auto',
        'entrance': 'closed', 'state_basis': 'actuator',
        'temperature_on': 29., 'temperature_off': 29., **changes}


def uno2_state(**changes):
    return {'board': 'UNO2', 'type': 'state', 'garage': 'closed', 'rfid_ok': True,
            'rfid_restricted': True, 'state_basis': 'actuator', **changes}


def test_debug_logs_do_not_become_state_or_acknowledgements():
    assert parse_serial_line(b'Entrance door opened.\n') is None
    assert parse_serial_line('DNB1 ' + json.dumps(uno1_state())) == uno1_state()
    with pytest.raises(ValueError):
        parse_serial_line(b'DNB1 ' + b'x'*2048)


def test_unbounded_integer_and_deep_json_are_recoverable_frame_errors():
    bad = 'DNB1 ' + json.dumps(uno1_state(light=10**400))
    assert len(bad.encode()) < 2048
    with pytest.raises(ValueError):
        parse_serial_line(bad)
    with pytest.raises(ValueError):
        parse_serial_line('DNB1 ' + '['*1000 + '0' + ']'*1000)
    assert parse_serial_line('DNB1 ' + json.dumps(uno1_state()))['type'] == 'state'


@pytest.mark.parametrize('changes', [
    {'temperature': float('nan')}, {'light': True}, {'humidity': 150},
    {'brightness': -1}, {'lamp_mode': {}}, {'dht_ok': 'true'},
    {'state_basis': 'limit_switch'}, {'board': 'UNO2'},
])
def test_invalid_or_wrong_board_state_is_rejected(changes):
    with pytest.raises(ValueError):
        normalize_message('uno1', uno1_state(**changes))


def test_failed_dht_does_not_refresh_old_temperature_or_humidity():
    result = normalize_message('uno1', uno1_state(dht_ok=False, temperature=None, humidity=None))
    assert result[0]['state'] == {'light': 600}
    with pytest.raises(ValueError):
        normalize_message('uno1', uno1_state(dht_ok=False))


def test_controller_positions_and_local_events_are_explicit():
    garage = normalize_message('uno2', uno2_state(garage='moving'))[0]
    assert garage['state'] == {'position': 'moving', 'state_basis': 'actuator'}
    assert normalize_message('uno1', {'board': 'UNO1', 'type': 'event', 'event': 'keypad_denied'})[0]['event'] == 'keypad_denied'
    with pytest.raises(ValueError):
        normalize_message('uno1', {'board': 'UNO1', 'type': 'event', 'event': 'rfid_granted'})


def command(device_id, action='set', **params):
    return {'command_id': 'a'*32, 'device_id': device_id, 'action': action, 'params': params}


def test_wire_mapping_routes_boards_and_resolves_toggle_only_once():
    wire = command_to_wire(command('front_door', 'toggle'), {'position': 'closed'})
    assert wire['board_id'] == 'uno1' and wire['opcode'] == 'DOOR_OPEN'
    assert encode_command(wire) == ('DNB1 '+'a'*32+' DOOR_OPEN\n').encode()
    assert command_to_wire(command('garage_door', position='closed'), {})['board_id'] == 'uno2'
    assert command_to_wire(command('main_light', power=True, brightness=80), {})['args'] == [80]
    assert command_to_wire(command('exhaust_fan', power=False), {})['opcode'] == 'FAN_OFF'


@pytest.mark.parametrize('cmd,state', [
    (command('garage_door', 'toggle'), {'position': 'moving'}),
    (command('main_light', power=False, brightness=80), {}),
    (command('main_light', power=True, brightness=0), {}),
    (command('window_1', position='closed'), {}),
    (command('exhaust_fan', mode='auto', power=True), {}),
])
def test_unsupported_or_conflicting_actions_are_not_silently_changed(cmd, state):
    with pytest.raises(ValueError):
        command_to_wire(cmd, state)


def test_serial_encoder_rejects_injected_or_invalid_opcodes_and_arguments():
    with pytest.raises(ValueError):
        encode_command({'command_id': 'a'*32, 'opcode': 'DOOR_OPEN\nOPEN'})
    with pytest.raises(ValueError):
        encode_command({'command_id': 'a'*32, 'opcode': 'BRIGHTNESS', 'args': [True]})
    with pytest.raises(ValueError):
        encode_command({'command_id': 'a'*32, 'opcode': 'TEMP_LIMITS', 'args': [29, 29]})


def test_gateway_auto_and_manual_modes_map_to_explicit_native_operations():
    assert command_to_wire(command('main_light', mode='auto'), {})['opcode'] == 'LIGHT_AUTO'
    assert command_to_wire(command('exhaust_fan', mode='auto'), {})['opcode'] == 'FAN_AUTO'
    assert command_to_wire(command('main_light', mode='manual'),
                           {'power': True, 'brightness': 60})['args'] == [60]
    assert command_to_wire(command('exhaust_fan', mode='manual'), {'power': False})['opcode'] == 'FAN_OFF'
    assert command_to_wire(command('main_light', mode='manual', brightness=30), {})['opcode'] == 'BRIGHTNESS'
    with pytest.raises(ValueError):
        command_to_wire(command('main_light', mode='manual'), {})


def test_installed_fan_lamp_and_pin_extensions_round_trip_to_wire():
    cases = [
        (command('exhaust_fan', speed=0), {}, 'FAN_SPEED', [0]),
        (command('main_light', color='#12abEF'), {}, 'LAMP_COLOR', [18,171,239]),
        (command('main_light', led_count=2), {}, 'LAMP_COUNT', [2]),
        (command('main_light', color='#12abEF', led_count=8), {}, 'LAMP_RGB', [18,171,239,8]),
        (command('front_door', pin='0123'), {}, 'ENTRANCE_PIN', ['0123']),
        (command('garage_door', pin='9876'), {}, 'GARAGE_PIN', ['9876']),
    ]
    for cmd, state, opcode, args in cases:
        wire = command_to_wire(cmd, state)
        assert wire['opcode'] == opcode and wire['args'] == args
        assert encode_command(wire) == ('DNB1 '+'a'*32+' '+opcode+' '+' '.join(map(str,args))+'\n').encode()
    records = normalize_message('uno1', uno1_state(
        fan_speed=70, lamp_color='#ff0088', lamp_count=8))
    assert records[1]['state']['color'] == '#FF0088'
    assert records[1]['state']['led_count'] == 8
    assert records[2]['state']['speed'] == 70


@pytest.mark.parametrize('cmd,state', [
    (command('exhaust_fan', speed=True), {}),
    (command('exhaust_fan', speed=101), {}),
    (command('exhaust_fan', speed=50, power=True), {}),
    (command('main_light', color='#010203', led_count=9), {}),
    (command('main_light', color='#010203', led_count=3, brightness=40), {}),
    (command('main_light', color='red', led_count=3), {}),
    (command('front_door', pin=1234), {}),
    (command('front_door', pin='１２３４'), {}),
    (command('front_door', pin='1234\nOPEN'), {}),
    (command('front_door', pin='1234', position='open'), {}),
    (command('main_light', pin='1234'), {}),
])
def test_extensions_reject_injection_and_nonatomic_combinations(cmd, state):
    with pytest.raises(ValueError):
        command_to_wire(cmd, state)


@pytest.mark.parametrize('opcode,args', [
    ('FAN_SPEED', [True]), ('LAMP_RGB', [0,0,0,0]),
    ('LAMP_RGB', [256,0,0,8]), ('ENTRANCE_PIN', ['1234\nOPEN']),
    ('LAMP_COLOR', [0,0,256]), ('LAMP_COLOR', [0,0]),
    ('LAMP_COUNT', [0]), ('LAMP_COUNT', [True]), ('LAMP_COUNT', [9]),
    ('GARAGE_PIN', [1234]),
])
def test_extension_encoder_validates_every_wire_argument(opcode, args):
    with pytest.raises(ValueError):
        encode_command({'command_id': 'a'*32, 'opcode': opcode, 'args': args})
