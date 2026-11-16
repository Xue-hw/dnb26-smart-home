"""Relay two identified USB UNO controllers to the project HTTP backend.

Run from the repository root with Python -m integrations.hardware.gateway.client.
No serial port is opened until the operator supplies its explicit COM/device name.
"""
from __future__ import annotations

import argparse
from collections import deque
import logging
import os
import threading
import time
import uuid
from urllib.parse import urlsplit

import httpx

from backend.hardware.uno_protocol import encode_command, parse_serial_line


LOG = logging.getLogger('dnb26.gateway')


class LineFramer:
    """Keep fragmented 9600-baud lines across read timeouts; discard overflow."""

    def __init__(self):
        self.buffer = bytearray()
        self.overflow = False

    def feed(self, data):
        lines = []
        for value in data:
            if value == 10:
                if not self.overflow:
                    lines.append(bytes(self.buffer).rstrip(b'\r'))
                self.buffer.clear()
                self.overflow = False
            elif not self.overflow:
                if len(self.buffer) >= 2048:
                    self.buffer.clear()
                    self.overflow = True
                else:
                    self.buffer.append(value)
        return lines


class BoardLink:
    def __init__(self, board_id, port, stop):
        self.board_id, self.port, self.stop = board_id, port, stop
        self.lock = threading.RLock()
        self.connection = None
        self.identified = False
        self.last_state = 0.
        self.messages = deque(maxlen=16)
        self.state = {}
        self.generation = 0
        self.connection_id = str(uuid.uuid4())
        self.thread = None
        self.config_pending = None
        self.last_config_attempt = 0.
        self.last_write = 0.
        self.write_lock = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self.run, name=f'usb-{self.board_id}', daemon=True)
        self.thread.start()

    def online(self):
        return bool(self.connection is not None and self.identified
                    and 0 <= time.monotonic()-self.last_state < 8)

    def snapshot(self):
        with self.lock:
            online = self.online()
            now = time.monotonic()
            messages = [(stamp, value) for stamp, value in self.messages if now-stamp < 1.5] if online else []
            self.messages.clear()
            return {'board_id': self.board_id, 'connected': online,
                    'connection_id': self.connection_id,
                    'age_ms': round(max((now-stamp for stamp, _ in messages), default=0)*1000, 1),
                    'messages': [value for _, value in messages]}, self.generation

    def accept(self, message):
        if message['board'].lower() != self.board_id:
            raise ValueError('串口身份与指定板卡不匹配')
        with self.lock:
            if message['type'] == 'identity':
                if self.identified:
                    # A controller RESET may keep its USB-UART connection open.
                    self.generation += 1
                    self.connection_id = str(uuid.uuid4())
                    self.last_state = 0.
                    self.messages.clear()
                    self.state = {}
                    self.config_pending = None
                self.identified = True
                LOG.info('%s identity verified', self.board_id)
            if not self.identified:
                return
            if message['type'] == 'state':
                self.last_state = time.monotonic()
                self.state = message
            if message['type'] == 'ack' and self.config_pending and message['command_id'] == self.config_pending:
                self.config_pending = None
                if message['status'] != 'acked':
                    LOG.warning('%s rejected temperature configuration', self.board_id)
                return
            self.messages.append((time.monotonic(), message))

    def send(self, command, deadline, generation):
        raw = encode_command(command)
        wire_seconds = len(raw)*10/9600
        # UNO RX is 64 bytes; each ACK is followed by a long state frame.
        # Serialize board writes without retrying commands or extending their TTL.
        with self.write_lock:
            with self.lock:
                pause = max(0., self.last_write + 1.1 - time.monotonic())
            if time.monotonic()+pause+wire_seconds+.05 >= deadline:
                return False
            if pause and self.stop.wait(pause):
                return False
            with self.lock:
                if (not self.online() or self.generation != generation
                        or time.monotonic()+wire_seconds+.05 >= deadline):
                    return False
                written = self.connection.write(raw)
                self.last_write = time.monotonic()
                if written != len(raw):
                    raise OSError('串口命令写入不完整，禁止重发')
                return True

    def sync_settings(self, settings, generation):
        if self.board_id != 'uno1' or settings.get('config_sync') is not True:
            return
        on, off = settings.get('temperature_on'), settings.get('temperature_off')
        if type(on) not in (int, float) or type(off) not in (int, float) or not -20 <= off < on <= 80:
            raise ValueError('无效温控设置')
        with self.lock:
            now = time.monotonic()
            if (self.state.get('temperature_on') == on and self.state.get('temperature_off') == off
                    or now-self.last_config_attempt < 5):
                return
            command_id = uuid.uuid4().hex
            self.last_config_attempt = now
            self.config_pending = command_id
        sent = self.send({'command_id': command_id, 'opcode': 'TEMP_LIMITS', 'args': [on, off]}, now+2.5, generation)
        if not sent:
            with self.lock:
                if self.config_pending == command_id:
                    self.config_pending = None

    def run(self):
        import serial
        while not self.stop.is_set():
            connection = None
            try:
                connection = serial.Serial(self.port, 9600, timeout=.1, write_timeout=.2)
                with self.lock:
                    self.connection = connection
                    self.identified = False
                    self.last_state = 0
                    self.generation += 1
                    self.connection_id = str(uuid.uuid4())
                    self.messages.clear()
                    self.state = {}
                    self.config_pending = None
                # Opening USB often resets an UNO. Probe identity after its bootloader.
                if self.stop.wait(2):
                    break
                framer = LineFramer()
                last_probe = 0.
                while not self.stop.is_set():
                    now = time.monotonic()
                    if now-last_probe >= 2 and (not self.identified or now-self.last_state >= 3):
                        if self.write_lock.acquire(blocking=False):
                            try:
                                with self.lock:
                                    if now-self.last_write >= 1.1:
                                        connection.write(b'STATE\n' if self.identified else b'ID\n')
                                        self.last_write = time.monotonic()
                                        last_probe = now
                            finally:
                                self.write_lock.release()
                    data = connection.read(min(connection.in_waiting or 1, 512))
                    for line in framer.feed(data):
                        try:
                            message = parse_serial_line(line)
                        except (ValueError, UnicodeError):
                            LOG.warning('%s discarded an invalid protocol frame', self.board_id)
                            continue
                        if message is not None:
                            self.accept(message)
            except (serial.SerialException, OSError, ValueError) as exc:
                LOG.warning('%s serial disconnected (%s)', self.board_id, type(exc).__name__)
            finally:
                with self.lock:
                    self.connection = None
                    self.identified = False
                    self.last_state = 0
                    self.messages.clear()
                    self.generation += 1
                if connection is not None:
                    connection.close()
            self.stop.wait(2)


def exchange_once(client, links, session, sequence):
    snapshots = {board: link.snapshot() for board, link in links.items()}
    started = time.monotonic()
    response = client.post('/api/hardware/gateway/exchange', json={
        'session_id': session, 'exchange_id': sequence,
        'boards': [value[0] for value in snapshots.values()]})
    response.raise_for_status()
    try:
        result = response.json()
    except RecursionError as exc:
        raise ValueError('后端网关JSON嵌套过深') from exc
    if not isinstance(result, dict):
        raise ValueError('后端网关响应必须是对象')
    commands = result.get('commands', [])
    if not isinstance(commands, list) or len(commands) > 32:
        raise ValueError('后端命令批次无效')
    for command in commands:
        if not isinstance(command, dict) or command.get('board_id') not in links:
            raise ValueError('后端命令目标无效')
        ttl = command.get('ttl_ms')
        if type(ttl) not in (int, float) or not 0 < ttl <= 5000:
            raise ValueError('后端命令有效期无效')
        link = links[command['board_id']]
        # Count the entire HTTP round trip against the remaining lifetime.
        if not link.send(command, started+ttl/1000, snapshots[command['board_id']][1]):
            LOG.warning('%s command discarded before USB write; backend will time out', link.board_id)
    settings = result.get('settings', {})
    if not isinstance(settings, dict):
        raise ValueError('后端设置无效')
    if 'uno1' in links and not any(command['board_id'] == 'uno1' for command in commands):
        links['uno1'].sync_settings(settings, snapshots['uno1'][1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://192.168.137.2:8080')
    parser.add_argument('--uno1', help='UNO1 USB serial port, e.g. COM3')
    parser.add_argument('--uno2', help='UNO2 USB serial port, e.g. COM4')
    parser.add_argument('--list-ports', action='store_true', help='List ports without opening them')
    parser.add_argument('--ca', help='PEM certificate to trust for the project HTTPS endpoint')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    if args.list_ports:
        from serial.tools import list_ports
        for port in list_ports.comports():
            print(f'{port.device}: {port.description} [USB serial: {port.serial_number or "unknown"}]')
        return
    token = os.getenv('DNB_GATEWAY_TOKEN', '')
    address = urlsplit(args.backend)
    if (address.scheme not in ('http', 'https') or not address.hostname or address.username or address.password
            or address.path not in ('', '/') or address.query or address.fragment):
        parser.error('--backend must be an HTTP(S) origin without credentials or path')
    if not token:
        parser.error('Set DNB_GATEWAY_TOKEN in the process environment, not on the command line')
    ports = {board: port for board, port in (('uno1', args.uno1), ('uno2', args.uno2)) if port}
    if not ports or len({value.casefold() for value in ports.values()}) != len(ports):
        parser.error('Supply distinct --uno1/--uno2 serial ports; one board may be omitted')
    verify = True
    if args.ca:
        import ssl
        verify = ssl.create_default_context(cafile=args.ca)
    stop = threading.Event()
    links = {board: BoardLink(board, port, stop) for board, port in ports.items()}
    for link in links.values():
        link.start()
    try:
        session, sequence = str(uuid.uuid4()), 0
        with httpx.Client(base_url=args.backend.rstrip('/'), timeout=1, verify=verify,
                          headers={'Authorization': 'Bearer '+token}, follow_redirects=False, trust_env=False) as client:
            while not stop.is_set():
                sequence += 1
                try:
                    exchange_once(client, links, session, sequence)
                except httpx.HTTPStatusError as exc:
                    LOG.error('Gateway endpoint rejected exchange: HTTP %s', exc.response.status_code)
                    if exc.response.status_code in (401, 403, 404, 409):
                        raise SystemExit('Fix gateway authorization/mode/session before restarting') from None
                except (httpx.HTTPError, ValueError, OSError) as exc:
                    LOG.warning('Exchange failed (%s); no buffered commands will be replayed', type(exc).__name__)
                stop.wait(.2)
    except KeyboardInterrupt:
        LOG.info('Stopping gateway')
    finally:
        stop.set()
        for link in links.values():
            if link.thread:
                link.thread.join(timeout=3)


if __name__ == '__main__':
    main()
