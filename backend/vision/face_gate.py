"""A door-feedback cooldown independent of camera and blink-session lifetime."""
import threading
import time


class FaceGateCooldown:
    def __init__(self):
        self.lock = threading.RLock()
        self._generation = 0
        self._cycle = None
        self._last_door_sample = float('-inf')

    @property
    def generation(self):
        with self.lock:
            return self._generation

    def snapshot(self):
        with self.lock:
            cycle = self._cycle
            phase = ('waiting_close' if cycle['opened'] else
                     'unknown' if cycle['unknown'] else 'waiting_open') if cycle else 'idle'
            return {'active': cycle is not None, 'phase': phase,
                    'command_id': cycle['command_id'] if cycle else None,
                    'generation': self._generation}

    def reserve(self, generation, *, now=None):
        with self.lock:
            if self._cycle is not None or generation != self._generation:
                return None
            self._generation += 1
            self._cycle = {'token': self._generation, 'command_id': None,
                           'started': time.monotonic() if now is None else now,
                           'dispatched': None, 'opened': False, 'unknown': False}
            return self._generation

    def bind(self, token, command_id):
        with self.lock:
            if self._cycle and self._cycle['token'] == token:
                self._cycle['command_id'] = command_id

    def dispatched(self, command_id, *, now=None):
        with self.lock:
            if (self._cycle and self._cycle['command_id'] == command_id
                    and self._cycle['dispatched'] is None):
                self._cycle['dispatched'] = time.monotonic() if now is None else now

    def _release(self):
        self._cycle = None
        self._generation += 1
        return True

    def cancel_unbound(self, token):
        with self.lock:
            if (self._cycle and self._cycle['token'] == token
                    and self._cycle['command_id'] is None):
                return self._release()
            return False

    def command_result(self, command_id, status, *, now=None):
        with self.lock:
            if not self._cycle or self._cycle['command_id'] != command_id:
                return False
            if status == 'acked':
                self.dispatched(command_id, now=now)
            elif status == 'failed' and not self._cycle['opened']:
                return self._release()
            elif status == 'timeout':
                self._cycle['unknown'] = True
            return False

    def observe(self, position, *, received_at=None):
        now = time.monotonic() if received_at is None else received_at
        with self.lock:
            if position not in ('open', 'closed') or now < self._last_door_sample:
                return False
            self._last_door_sample = now
            if self._cycle is None:
                if position == 'open':
                    self.reserve(self._generation, now=now)
                    self._cycle.update(dispatched=now, opened=True)
                return False
            cycle = self._cycle
            if cycle['dispatched'] is None or now < cycle['dispatched']:
                return False
            if position == 'open':
                cycle['opened'] = True
            elif cycle['opened']:
                return self._release()
            return False
