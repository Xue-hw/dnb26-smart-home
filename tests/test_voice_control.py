"""Voice reception is a real UNO1 capability, never inferred from legacy frames."""
from types import SimpleNamespace

import pytest

from backend.hardware.gateway_bridge import GatewayBridge
from backend.hardware.uno_protocol import command_to_wire, encode_command, normalize_message
from backend.runtime import Runtime


def state(**changes):
    return {'board':'UNO1','type':'state','temperature':25.,'humidity':45.,'light':600,
            'dht_ok':True,'lamp_power':True,'brightness':80,'lamp_mode':'manual',
            'fan_power':False,'fan_mode':'auto','entrance':'closed','state_basis':'actuator',
            'temperature_on':30.,'temperature_off':28.,**changes}


@pytest.mark.parametrize('enabled,opcode', [(True,'VOICE_ON'),(False,'VOICE_OFF')])
def test_voice_toggle_has_a_dedicated_uno1_wire_command(enabled, opcode):
    command = {'command_id':'a'*32,'device_id':'voice_control','action':'set','params':{'power':enabled}}
    wire = command_to_wire(command, {'power':not enabled})
    assert wire == {'command_id':'a'*32,'board_id':'uno1','opcode':opcode,'args':[]}
    assert encode_command(wire) == ('DNB1 '+'a'*32+' '+opcode+'\n').encode()
    command.update(action='toggle',params={})
    assert command_to_wire(command, {'power':not enabled}) == wire


def test_legacy_uno1_state_does_not_invent_voice_enabled():
    assert not any(row.get('device_id')=='voice_control' for row in normalize_message('uno1',state()))
    for enabled in (False,True):
        voice = next(row for row in normalize_message('uno1',state(voice_enabled=enabled)) if row.get('device_id')=='voice_control')
        assert voice['state'] == {'power':enabled}
    with pytest.raises(ValueError):
        normalize_message('uno1',state(voice_enabled='false'))


def test_gateway_voice_requires_fresh_advertised_support():
    bridge = GatewayBridge(SimpleNamespace(options={'temperature_on':30.,'temperature_off':28.}))
    bridge.board_online = lambda board: board == 'uno1'
    assert bridge.device_online('main_light')
    assert not bridge.device_online('voice_control')
    assert 'voice_control' not in bridge.details()['uno1']['capabilities']
    bridge.session_id = 'test-session'
    with pytest.raises(RuntimeError, match='固件'):
        bridge.send({'command_id':'a'*32,'device_id':'voice_control','action':'set','params':{'power':False}})
    bridge.boards['uno1']['state'] = state(voice_enabled=True)
    assert bridge.device_online('voice_control')
    assert 'voice_control' in bridge.details()['uno1']['capabilities']
    bridge.board_online = lambda board: False
    assert not bridge.device_online('voice_control')


def test_voice_validation_preserves_other_control_semantics():
    assert Runtime.validate_command('voice','set',{'power':False},allow_mode=True) == {'power':False}
    for params in ({'power':1},{'mode':'auto'},{'power':False,'mode':'manual'}):
        with pytest.raises(ValueError):
            Runtime.validate_command('voice','set',params,allow_mode=True)
