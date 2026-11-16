"""One authenticated PC session relays two independent USB controllers.

Commands are bounded, short-lived and consumed on HTTP delivery. Losing a
response must never replay an earlier door-open command after a reconnect.
"""
from __future__ import annotations

from collections import OrderedDict
import math
import threading
import time
import uuid

from backend.hardware.uno_protocol import BOARDS, CAPABILITIES, DEVICE_BOARDS, command_to_wire, normalize_message


class GatewayBridge:
    BOARD_TIMEOUT = 10.
    MESSAGE_MAX_AGE_MS = 2000
    COMMAND_TTL = 5.
    MAX_PENDING = 32

    def __init__(self, runtime):
        self.runtime = runtime
        self.lock = threading.RLock()
        self.exchange_lock = threading.Lock()
        self.session_id = None
        self.retired_sessions = set()
        self.exchange_id = -1
        self.last_exchange = 0.
        self.boards = {board: {'connected': False, 'last_seen': 0., 'state': {}, 'connection_id': None} for board in BOARDS}
        self.states = {}
        self.pending = OrderedDict()
        self.delivered = {}
        self.next_delivery = {board: 0. for board in BOARDS}

    def board_online(self, board_id):
        with self.lock:
            board = self.boards.get(board_id)
            now = time.monotonic()
            return bool(board and board['connected'] and 0 <= now-board['last_seen'] < self.BOARD_TIMEOUT
                        and 0 <= now-self.last_exchange < self.BOARD_TIMEOUT)

    @property
    def online(self):
        return all(self.board_online(board) for board in BOARDS)

    def details(self):
        with self.lock:
            result = {}
            for board_id, board in self.boards.items():
                online = self.board_online(board_id)
                state = board['state']
                detail = {'status': 'online' if online else 'offline',
                          'message': 'USB控制器状态持续上报' if online else '电脑网关或UNO状态未更新',
                          'capabilities': [device for device, owner in DEVICE_BOARDS.items() if owner == board_id]}
                for key in ('dht_ok', 'rfid_ok', 'rfid_restricted', 'temperature_on', 'temperature_off'):
                    if key in state:
                        detail[key] = state[key]
                if board_id == 'uno1':
                    detail['temperature_config_synced'] = online and all(
                        type(state.get(key)) in (int, float)
                        and abs(state[key]-self.runtime.options[key]) < .01
                        for key in ('temperature_on', 'temperature_off'))
                result[board_id] = detail
            return result

    def device_online(self, device_id):
        return self.board_online(DEVICE_BOARDS.get(device_id))

    def sensor_valid(self, metric):
        with self.lock:
            if metric in ('temperature', 'humidity'):
                return self.boards['uno1']['state'].get('dht_ok') is True
            return metric == 'light'

    def _finish(self, command_id, status, reason):
        command = self.runtime.repository.finish_command(command_id, status, reason)
        self.runtime.events.publish('command.updated', command)

    def _forget_board_commands(self, board_id, reason):
        for cid, item in list(self.pending.items()):
            if item['wire']['board_id'] == board_id:
                self._finish(cid, 'failed', reason)
                del self.pending[cid]
        for cid, item in list(self.delivered.items()):
            if item['board_id'] == board_id:
                self._finish(cid, 'timeout', reason + '；已发送命令的实际结果未知')
                del self.delivered[cid]

    def send(self, command, capture=None):
        with self.lock:
            board = DEVICE_BOARDS.get(command.get('device_id'))
            if not self.session_id or not self.board_online(board):
                raise RuntimeError('目标UNO未连接或实时状态已过期')
            if len(self.pending) >= self.MAX_PENDING:
                raise RuntimeError('硬件命令队列已满，请等待回执')
            state = self.states.get(command['device_id'], {})
            wire = command_to_wire(command, state)
            now = time.monotonic()
            expires = now + self.COMMAND_TTL
            if capture is not None:
                if not self.runtime.camera.is_current_capture(*capture):
                    raise RuntimeError('摄像头会话已变化或当前图像已过期')
                expires = min(expires, capture[0] + self.runtime.camera.ACTION_FRAME_MAX_AGE)
            self.pending[command['command_id']] = {'wire': wire, 'expires': expires,
                'capture': capture, 'session_id': self.session_id}

    def exchange(self, payload):
        """Validate the whole batch before applying telemetry or consuming commands."""
        if not isinstance(payload, dict):
            raise ValueError('网关消息必须是对象')
        session = payload.get('session_id')
        try:
            if not isinstance(session, str) or str(uuid.UUID(session)) != session:
                raise ValueError('网关session_id必须是标准UUID')
        except (ValueError, AttributeError) as exc:
            raise ValueError('无效网关session_id') from exc
        sequence = payload.get('exchange_id', 0)
        if type(sequence) is not int or not 0 <= sequence < 2**53:
            raise ValueError('无效网关exchange_id')
        boards = payload.get('boards')
        if not isinstance(boards, list) or len(boards) > 2:
            raise ValueError('网关最多上报两块UNO')
        checked, seen = [], set()
        for board in boards:
            if not isinstance(board, dict) or board.get('board_id') not in BOARDS:
                raise ValueError('未知网关板卡')
            board_id = board['board_id']
            if board_id in seen or type(board.get('connected')) is not bool:
                raise ValueError('板卡重复或连接状态无效')
            seen.add(board_id)
            messages = board.get('messages', [])
            age = board.get('age_ms', 0)
            connection = board.get('connection_id')
            if connection is not None and (not isinstance(connection, str) or len(connection) > 64 or not connection):
                raise ValueError('无效串口连接编号')
            if type(age) not in (int, float) or not math.isfinite(age) or not 0 <= age <= self.MESSAGE_MAX_AGE_MS:
                raise ValueError('网关消息过期，请丢弃旧串口缓冲')
            if not isinstance(messages, list) or len(messages) > 16 or (not board['connected'] and messages):
                raise ValueError('无效网关消息批次')
            normalized = [(message, normalize_message(board_id, message)) for message in messages]
            checked.append((board_id, board['connected'], normalized, age, connection))
        with self.exchange_lock:
            return self._exchange_checked(session, sequence, checked)

    def _exchange_checked(self, session, sequence, checked):
        callbacks = []
        with self.lock:
            if session in self.retired_sessions:
                raise RuntimeError('网关会话已被新进程替换，请重新启动网关')
            if session != self.session_id:
                if self.session_id is not None:
                    self.retired_sessions.add(self.session_id)
                    for board in BOARDS:
                        self._forget_board_commands(board, '电脑网关会话已更换，取消旧命令')
                self.session_id, self.exchange_id = session, -1
                self.states.clear()
                for board in self.boards.values():
                    board.update(connected=False, last_seen=0., state={}, connection_id=None)
            if sequence <= self.exchange_id:
                raise ValueError('网关批次重复或乱序，禁止重放')
            self.exchange_id = sequence
            now = time.monotonic()
            # A long transport gap invalidates pending commands even if the same PC
            # process reconnects with its previous UUID.
            if self.last_exchange and now-self.last_exchange >= self.BOARD_TIMEOUT:
                for board in BOARDS:
                    self._forget_board_commands(board, '网关连接中断，取消旧命令')
            self.last_exchange = now
            for board_id, connected, messages, age, connection in checked:
                board = self.boards[board_id]
                replaced = connection is not None and board['connection_id'] not in (None, connection)
                if not connected or replaced:
                    self._forget_board_commands(board_id, 'USB控制器已断开，取消旧命令')
                    board.update(last_seen=0., state={})
                    for device, owner in DEVICE_BOARDS.items():
                        if owner == board_id:
                            self.states.pop(device, None)
                board['connected'] = connected
                board['connection_id'] = connection
                for message, items in messages:
                    if message['type'] == 'state':
                        board['last_seen'] = now-age/1000
                        board['state'] = dict(message)
                    for item in items:
                        if item['type'] == 'ack':
                            delivery = self.delivered.get(item['command_id'])
                            if not delivery or delivery['session_id'] != session or delivery['board_id'] != board_id:
                                continue
                            command = self.runtime.repository.command(item['command_id'])
                            if command['status'] == 'pending':
                                callbacks.append(item)
                            del self.delivered[item['command_id']]
                        elif item['type'] == 'local_event':
                            callbacks.append(item)
                        else:
                            self.states[item['device_id']] = item['state']
                            callbacks.append(item)
        # Telemetry can enter Runtime.send_command (temperature automation).
        # Never hold the bridge lock while acquiring Runtime.command_lock.
        for item in callbacks:
            self.runtime.on_gateway_message(item)
        with self.lock:
            commands = []
            for cid, item in list(self.pending.items()):
                board_id = item['wire']['board_id']
                command = self.runtime.repository.command(cid)
                reason = None
                if command['status'] != 'pending':
                    del self.pending[cid]
                    continue
                if item['session_id'] != session or not self.board_online(board_id):
                    reason = '目标UNO不在线，取消旧命令'
                elif time.monotonic() >= item['expires']:
                    reason = '命令等待过久，已取消；不会在重连后重放'
                elif item['capture'] is not None and not self.runtime.camera.is_current_capture(*item['capture']):
                    reason = '实时图像或摄像头会话已失效，取消联动命令'
                if reason:
                    del self.pending[cid]
                    self._finish(cid, 'failed', reason)
                    continue
                if (time.monotonic() < self.next_delivery[board_id]
                        or any(delivery['board_id'] == board_id for delivery in self.delivered.values())):
                    continue
                del self.pending[cid]
                ttl = int((item['expires']-time.monotonic())*1000)
                if ttl <= 0:
                    self._finish(cid, 'failed', '命令已过期，取消发送')
                    continue
                commands.append({**item['wire'], 'ttl_ms': ttl})
                self.next_delivery[board_id] = time.monotonic()+1.1
                self.delivered[cid] = {'session_id': session, 'board_id': board_id, 'delivered_at': time.monotonic()}
            # ACK bookkeeping is bounded even if the board never answers.
            for cid, item in list(self.delivered.items()):
                if time.monotonic()-item['delivered_at'] > 30:
                    del self.delivered[cid]
            return {'commands': commands, 'settings': {'config_sync': True,
                    'temperature_on': self.runtime.options['temperature_on'],
                    'temperature_off': self.runtime.options['temperature_off']},
                    'boards': self.details()}

    def stop(self):
        with self.lock:
            for board in self.boards.values():
                board['connected'] = False
