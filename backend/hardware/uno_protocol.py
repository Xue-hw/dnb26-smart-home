"""Bounded, explicit protocol for the two project UNO controllers.

Unprefixed serial diagnostics are never treated as telemetry or acknowledgements.
Door positions here describe the actuator controller, not limit-switch feedback.
"""
from __future__ import annotations

import json
import math
import re


BOARDS = ('uno1', 'uno2')
DEVICE_BOARDS = {'front_door': 'uno1', 'main_light': 'uno1',
                 'exhaust_fan': 'uno1', 'thermometer_1': 'uno1',
                 'garage_door': 'uno2', 'voice_control': 'uno1'}
CAPABILITIES = {'front_door': ['position', 'pin'], 'garage_door': ['position', 'pin'],
                'main_light': ['power', 'brightness', 'mode', 'color', 'led_count'],
                'exhaust_fan': ['power', 'mode', 'speed'],
                'thermometer_1': ['temperature', 'humidity', 'light'], 'voice_control': ['power']}
EVENTS = {'keypad_granted', 'keypad_denied', 'voice', 'rfid_granted', 'rfid_denied'}
COMMAND_ID = re.compile(r'[0-9a-f]{32}')
COLOR = re.compile(r'#[0-9a-fA-F]{6}')
PIN = re.compile(r'[0-9]{4}')
RFID_UID = re.compile(r'(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{14}|[0-9a-fA-F]{20})')


def _number(value, low, high, name, integer=False):
    # Check bounds first: converting an arbitrarily large JSON integer to a
    # float inside isfinite() can itself overflow and kill a serial worker.
    if type(value) not in ((int,) if integer else (int, float)) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(f'无效硬件字段: {name}')
    return value


def _boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f'无效硬件布尔字段: {name}')
    return value


def _choice(value, choices, name):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f'无效硬件字段: {name}')
    return value


def _color(value):
    if not isinstance(value, str) or not COLOR.fullmatch(value):
        raise ValueError('颜色必须为#RRGGBB十六进制格式')
    return value.upper()


def _pin(value):
    if not isinstance(value, str) or not PIN.fullmatch(value):
        raise ValueError('门禁密码必须为4位数字')
    return value


def parse_serial_line(raw):
    """Return a DNB1 frame or None for the original human-readable diagnostics."""
    if isinstance(raw, bytes):
        if len(raw) > 2048:
            raise ValueError('硬件行超过2048字节')
        raw = raw.decode('utf-8', errors='strict')
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 2048:
        raise ValueError('无效或超长硬件行')
    if not raw.startswith('DNB1 '):
        return None
    def invalid_constant(value):
        raise ValueError('硬件JSON不允许非有限数值')
    try:
        message = json.loads(raw[5:], parse_constant=invalid_constant)
    except RecursionError as exc:
        raise ValueError('硬件JSON嵌套过深') from exc
    if not isinstance(message, dict):
        raise ValueError('硬件消息必须是对象')
    board = message.get('board')
    if board not in ('UNO1', 'UNO2'):
        raise ValueError('未知UNO板卡')
    normalize_message(board.lower(), message)
    return message


def normalize_message(board_id, message):
    """Validate one board frame and map it to bounded backend messages."""
    if board_id not in BOARDS or not isinstance(message, dict) or message.get('board') != board_id.upper():
        raise ValueError('UNO身份与串口归属不一致')
    kind = message.get('type')
    if kind == 'identity':
        if type(message.get('protocol')) is not int or message['protocol'] != 1:
            raise ValueError('不支持的UNO协议版本')
        return []
    if kind == 'ack':
        cid = message.get('command_id')
        if not isinstance(cid, str) or not COMMAND_ID.fullmatch(cid):
            raise ValueError('无效硬件命令编号')
        status = _choice(message.get('status'), ('acked', 'failed'), 'status')
        error = message.get('error')
        if error is not None and (not isinstance(error, str) or len(error) > 200):
            raise ValueError('硬件错误描述过长或无效')
        return [{'type': 'ack', 'command_id': cid, 'status': status, 'error': error}]
    if kind == 'event':
        event = _choice(message.get('event'), EVENTS, 'event')
        permitted = {'keypad_granted', 'keypad_denied', 'voice'} if board_id == 'uno1' else {'rfid_granted', 'rfid_denied'}
        if event not in permitted:
            raise ValueError('事件与UNO职责不一致')
        result = {'type': 'local_event', 'event': event, 'board_id': board_id}
        if 'command' in message:
            if event != 'voice':
                raise ValueError('只有语音事件可携带语音指令')
            result['command'] = _number(message['command'], 1, 6, 'command', integer=True)
        if 'uid' in message:
            uid = message['uid']
            if event not in ('rfid_granted','rfid_denied') or not isinstance(uid,str) or not RFID_UID.fullmatch(uid):
                raise ValueError('RFID UID必须为4、7或10字节连续十六进制值')
            result['uid'] = uid.upper()
        return [result]
    if kind != 'state' or message.get('state_basis') != 'actuator':
        raise ValueError('未知UNO消息或不支持的状态依据')
    if board_id == 'uno2':
        _boolean(message.get('rfid_ok'), 'rfid_ok')
        _boolean(message.get('rfid_restricted'), 'rfid_restricted')
        position = _choice(message.get('garage'), ('open', 'closed', 'moving'), 'garage')
        return [{'type': 'telemetry', 'device_id': 'garage_door',
                 'state': {'position': position, 'state_basis': 'actuator'}}]
    dht_ok = _boolean(message.get('dht_ok'), 'dht_ok')
    sensor = {'light': _number(message.get('light'), 0, 1023, 'light', integer=True)}
    if dht_ok:
        sensor.update(temperature=_number(message.get('temperature'), -40, 125, 'temperature'),
                      humidity=_number(message.get('humidity'), 0, 100, 'humidity'))
    else:
        # A failed DHT must not refresh old temperature/humidity values as new data.
        for key in ('temperature', 'humidity'):
            if message.get(key) is not None:
                raise ValueError('DHT故障时温湿度必须上报null')
    light = {'power': _boolean(message.get('lamp_power'), 'lamp_power'),
             'brightness': _number(message.get('brightness'), 0, 100, 'brightness', integer=True),
             'mode': _choice(message.get('lamp_mode'), ('auto', 'manual'), 'lamp_mode')}
    fan = {'power': _boolean(message.get('fan_power'), 'fan_power'),
           'mode': _choice(message.get('fan_mode'), ('auto', 'manual'), 'fan_mode')}
    # Older protocol-v1 state frames remain readable during firmware upgrades.
    if 'fan_speed' in message:
        fan['speed'] = _number(message['fan_speed'], 0, 100, 'fan_speed', integer=True)
    if 'lamp_color' in message:
        light['color'] = _color(message['lamp_color'])
    if 'lamp_count' in message:
        light['led_count'] = _number(message['lamp_count'], 1, 8, 'lamp_count', integer=True)
    position = _choice(message.get('entrance'), ('open', 'closed'), 'entrance')
    for key in ('temperature_on', 'temperature_off'):
        _number(message.get(key), -20, 80, key)
    result = [{'type': 'telemetry', 'device_id': 'thermometer_1', 'state': sensor},
            {'type': 'telemetry', 'device_id': 'main_light', 'state': light},
            {'type': 'telemetry', 'device_id': 'exhaust_fan', 'state': fan},
            {'type': 'telemetry', 'device_id': 'front_door',
             'state': {'position': position, 'state_basis': 'actuator'}}]
    if 'voice_enabled' in message:
        result.append({'type': 'telemetry', 'device_id': 'voice_control',
                       'state': {'power': _boolean(message['voice_enabled'], 'voice_enabled')}})
    return result


def command_to_wire(command, state):
    """Resolve toggle once from current controller state; never replay a toggle."""
    device_id = command.get('device_id')
    if device_id not in DEVICE_BOARDS or device_id == 'thermometer_1':
        raise ValueError('当前两UNO没有此执行设备')
    action, params = command.get('action'), command.get('params', {})
    if action not in ('set', 'toggle') or not isinstance(params, dict):
        raise ValueError('无效UNO控制命令')
    if action == 'toggle':
        if params:
            raise ValueError('toggle不接受额外参数')
        if device_id in ('front_door', 'garage_door'):
            if state.get('position') not in ('open', 'closed'):
                raise ValueError('门当前状态未知或移动中，不能切换')
            params = {'position': 'closed' if state['position'] == 'open' else 'open'}
        else:
            if type(state.get('power')) is not bool:
                raise ValueError('设备开关状态未知，不能切换')
            params = {'power': not state['power']}
    allowed = set(CAPABILITIES[device_id])
    if not params or set(params) - allowed:
        raise ValueError('当前固件不支持此控制参数')
    if device_id == 'voice_control':
        enabled = _boolean(params.get('power'), 'power')
        return {'command_id':command['command_id'], 'board_id':'uno1',
                'opcode':'VOICE_ON' if enabled else 'VOICE_OFF', 'args':[]}
    special = set(params) & {'pin', 'speed', 'color', 'led_count'}
    if special:
        # Each operation is one atomic wire command. Never drop other parameters.
        if special == {'pin'} and set(params) == {'pin'}:
            opcode = 'ENTRANCE_PIN' if device_id == 'front_door' else 'GARAGE_PIN'
            args = [_pin(params['pin'])]
        elif special == {'speed'} and set(params) == {'speed'}:
            opcode, args = 'FAN_SPEED', [_number(params['speed'], 0, 100, 'speed', integer=True)]
        elif set(params) <= {'color', 'led_count'}:
            # Independent field operations preserve a concurrent change from
            # another client instead of filling it with stale telemetry.
            args = []
            if 'color' in params:
                color = _color(params['color'])
                args = [int(color[index:index+2], 16) for index in (1, 3, 5)]
            if 'led_count' in params:
                args.append(_number(params['led_count'], 1, 8, 'led_count', integer=True))
            opcode = 'LAMP_RGB' if len(params) == 2 else 'LAMP_COLOR' if 'color' in params else 'LAMP_COUNT'
        else:
            raise ValueError('调速、颜色/灯珠数、密码修改必须分别下发，不能混合其他控制参数')
        return {'command_id': command['command_id'], 'board_id': DEVICE_BOARDS[device_id],
                'opcode': opcode, 'args': args}
    mode = params.get('mode')
    if mode is not None:
        _choice(mode, ('auto', 'manual'), 'mode')
        if mode == 'auto':
            if set(params) != {'mode'}:
                raise ValueError('恢复自动模式不能同时设置开关或亮度')
            return {'command_id': command['command_id'], 'board_id': DEVICE_BOARDS[device_id],
                    'opcode': 'LIGHT_AUTO' if device_id == 'main_light' else 'FAN_AUTO', 'args': []}
        params = {key: value for key, value in params.items() if key != 'mode'}
        if not params:
            if type(state.get('power')) is not bool:
                raise ValueError('设备当前状态未知，无法保持当前输出切换手动')
            params = {'power': state['power']}
            if device_id == 'main_light':
                params['brightness'] = _number(state.get('brightness'), 0, 100, 'brightness', integer=True)
    args = []
    if device_id in ('front_door', 'garage_door'):
        position = _choice(params.get('position'), ('open', 'closed'), 'position')
        opcode = 'DOOR_OPEN' if position == 'open' else 'DOOR_CLOSE'
    elif device_id == 'exhaust_fan':
        opcode = 'FAN_ON' if _boolean(params.get('power'), 'power') else 'FAN_OFF'
    elif 'brightness' in params:
        brightness = _number(params['brightness'], 0, 100, 'brightness', integer=True)
        if 'power' in params and _boolean(params['power'], 'power') != (brightness > 0):
            raise ValueError('灯光开关与亮度相互冲突')
        opcode, args = 'BRIGHTNESS', [brightness]
    else:
        opcode = 'LIGHT_ON' if _boolean(params.get('power'), 'power') else 'LIGHT_OFF'
    return {'command_id': command['command_id'], 'board_id': DEVICE_BOARDS[device_id],
            'opcode': opcode, 'args': args}


def encode_command(command):
    """Encode only the command opcodes implemented by the integrated firmware."""
    cid, opcode, args = command.get('command_id'), command.get('opcode'), command.get('args', [])
    if not isinstance(cid, str) or not COMMAND_ID.fullmatch(cid):
        raise ValueError('无效硬件命令编号')
    if opcode not in ('DOOR_OPEN', 'DOOR_CLOSE', 'LIGHT_ON', 'LIGHT_OFF', 'BRIGHTNESS',
                       'LIGHT_AUTO', 'FAN_ON', 'FAN_OFF', 'FAN_AUTO', 'TEMP_LIMITS',
                       'FAN_SPEED', 'LAMP_RGB', 'LAMP_COLOR', 'LAMP_COUNT', 'ENTRANCE_PIN', 'GARAGE_PIN',
                       'VOICE_ON', 'VOICE_OFF'):
        raise ValueError('不支持的硬件操作码')
    if opcode in ('BRIGHTNESS', 'FAN_SPEED'):
        if not isinstance(args, list) or len(args) != 1:
            raise ValueError('无效亮度参数')
        _number(args[0], 0, 100, 'brightness', integer=True)
    elif opcode in ('ENTRANCE_PIN', 'GARAGE_PIN'):
        if not isinstance(args, list) or len(args) != 1:
            raise ValueError('无效密码参数')
        _pin(args[0])
    elif opcode in ('LAMP_RGB', 'LAMP_COLOR', 'LAMP_COUNT'):
        expected = {'LAMP_RGB': 4, 'LAMP_COLOR': 3, 'LAMP_COUNT': 1}[opcode]
        if not isinstance(args, list) or len(args) != expected:
            raise ValueError('无效RGB灯带参数')
        if opcode != 'LAMP_COUNT':
            for value in args[:3]:
                _number(value, 0, 255, 'color', integer=True)
        if opcode != 'LAMP_COLOR':
            _number(args[-1], 1, 8, 'led_count', integer=True)
    elif opcode == 'TEMP_LIMITS':
        if not isinstance(args, list) or len(args) != 2:
            raise ValueError('无效温控参数')
        for value in args:
            _number(value, -20, 80, 'temperature')
        if args[1] >= args[0]:
            raise ValueError('关闭温度必须小于开启温度')
    elif args != []:
        raise ValueError('此操作码不接受参数')
    return ('DNB1 ' + cid + ' ' + opcode + ''.join(' ' + str(arg) for arg in args) + '\n').encode('ascii')
