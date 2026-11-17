"""Line-delimited JSON bridge; requires matching Arduino firmware before use."""
import json
import threading
import time


class SerialBridge:
    def __init__(self, settings, on_message):
        self.settings, self.on_message = settings, on_message
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.connection = None
        self.last_seen = 0.
        self.error = '尚未接入 Arduino'
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._read, daemon=True, name='arduino-reader')
        self.thread.start()

    def _read(self):
        while not self.stop_event.is_set():
            try:
                import serial
                self.connection = serial.Serial(self.settings.serial_port, self.settings.serial_baud, timeout=1, write_timeout=2)
                while not self.stop_event.is_set():
                    raw = self.connection.read_until(b'\n', size=8193)
                    if not raw:
                        continue
                    if len(raw) > 8192 or not raw.endswith(b'\n'):
                        raise ValueError('Arduino 消息超长或未换行')
                    payload = json.loads(raw)
                    if not isinstance(payload, dict) or payload.get('type') not in ('heartbeat','telemetry','ack'):
                        raise ValueError('未知 Arduino 消息')
                    self.on_message(payload)
                    self.last_seen, self.error = time.monotonic(), ''
            except Exception as exc:
                self.error = f'Arduino 通信失败: {exc}'
            finally:
                if self.connection:
                    self.connection.close()
                self.connection = None
            self.stop_event.wait(3)

    @property
    def online(self):
        return self.connection is not None and time.monotonic()-self.last_seen < 10

    def send(self, command):
        if not self.online:
            raise RuntimeError('Arduino 未连接或心跳已过期')
        raw = (json.dumps({'type':'command', **command}, ensure_ascii=True)+'\n').encode()
        with self.lock:
            self.connection.write(raw)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=4)
