"""The camera bulb effect uses existing UNO commands and current captures."""
import time

import numpy as np
import pytest

from backend.config import Settings
from backend.runtime import Runtime


def effect_runtime(tmp_path):
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'))
    runtime.camera.status = 'online'
    runtime.camera.frame = np.zeros((16, 16, 3), dtype=np.uint8)
    runtime.models.detect = lambda frame: ([{'model': 'custom', 'label': 'light_bulb',
                                           'confidence': .9, 'bbox': [1, 1, 8, 8]}], 1.)
    runtime.record_live_event = lambda *args: None
    runtime.last_recognition = time.monotonic()
    runtime.bulb_count = 2
    commands = []
    def send(device, action, params, **kwargs):
        command = {'command_id': str(len(commands)), 'status': 'pending', 'params': params, **kwargs}
        commands.append(command)
        return command
    runtime.send_command = send
    runtime.repository.command = lambda cid: commands[int(cid)]
    return runtime, commands


def frame(runtime, *, live=True):
    runtime.camera.last_frame = time.monotonic()
    runtime.process_frame(runtime.camera.frame.copy(), 1, None, live,
                          captured_monotonic=runtime.camera.last_frame, generation=runtime.camera.generation)


def test_cyan_then_80_percent_requires_color_ack_and_new_fresh_bulb_frame(tmp_path, monkeypatch):
    # Explicit capture times avoid equal Windows clock ticks across distinct frames.
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    runtime, commands = effect_runtime(tmp_path)
    frame(runtime)
    assert [c['params'] for c in commands] == [{'color': '#00FFFF'}]
    frame(runtime)
    assert len(commands) == 1
    commands[0]['status'] = 'acked'
    clock[0] += .1
    frame(runtime)
    assert [c['params'] for c in commands] == [{'color': '#00FFFF'}, {'power': True, 'brightness': 80}]
    assert commands[1]['capture'][0] > commands[0]['capture'][0]
    assert all(c['source'] == 'bulb' and 'led_count' not in c['params'] for c in commands)
    frame(runtime)
    assert len(commands) == 2, 'existing ten-second cooldown must prevent repeated commands'


@pytest.mark.parametrize('interruption', ['failed', 'timeout', 'replay', 'no_bulb', 'new_generation'])
def test_interrupted_color_stage_never_turns_light_on(tmp_path, interruption):
    runtime, commands = effect_runtime(tmp_path)
    frame(runtime)
    commands[0]['status'] = interruption if interruption in ('failed', 'timeout') else 'acked'
    if interruption == 'no_bulb':
        runtime.models.detect = lambda image: ([], 1.)
    if interruption == 'new_generation':
        runtime.camera.generation += 1
    frame(runtime, live=interruption != 'replay')
    assert len(commands) == 1


def test_new_gui_light_command_cancels_waiting_bulb_effect(tmp_path):
    runtime = Runtime(Settings(data_dir=tmp_path, hardware_mode='gateway'))
    runtime.pending_bulb_effect = {'command_id': 'color-1', 'generation': 0, 'started': time.monotonic()}
    runtime.repository.create_command = lambda *args: ({'command_id': 'gui-1', 'status': 'pending'}, True)
    runtime.gateway.send = lambda *args, **kwargs: None
    runtime.send_command('main_light', 'set', {'power': False}, source='gui')
    assert runtime.pending_bulb_effect is None


@pytest.mark.parametrize('status', ['acked', 'pending'])
def test_color_stage_cannot_resume_after_five_seconds(tmp_path, status):
    runtime, commands = effect_runtime(tmp_path)
    frame(runtime)
    commands[0]['status'] = status
    runtime.pending_bulb_effect['started'] -= 6
    frame(runtime)
    assert len(commands) == 1
    assert runtime.pending_bulb_effect is None


def test_local_voice_light_command_cancels_waiting_bulb_effect(tmp_path):
    runtime=Runtime(Settings(data_dir=tmp_path,hardware_mode='gateway'))
    runtime.pending_bulb_effect={'command_id':'color-1'}
    runtime.repository.event=lambda *args,**kwargs:{}
    runtime.on_gateway_message({'type':'local_event','event':'voice','board_id':'uno1','command':4})
    assert runtime.pending_bulb_effect is None
