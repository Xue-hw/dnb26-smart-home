"""Shared overlay palette; presentation never changes the access decision."""
import json
from pathlib import Path


PALETTE = json.loads(Path(__file__).with_name('annotation_palette.json').read_text(encoding='utf-8'))


def object_annotation(detection):
    model = detection.get('model')
    return model if model in ('general', 'custom') else 'unknown'


def face_annotation(face):
    identity = face.get('identity_matched')
    status = face.get('liveness_status')
    if identity is False:
        key = 'face_unauthorized'
    elif identity is not True:
        key = 'unknown'
    elif status == 'passed':
        key = 'face_granted' if face.get('access_granted') is True else 'face_live'
    elif status == 'pending':
        key = 'face_pending'
    elif status in ('failed', 'timeout'):
        key = 'face_failed'
    elif status in ('unavailable', 'not_applicable'):
        key = 'face_unavailable'
    else:
        key = 'unknown'
    return key, PALETTE[key]['tag']


def bgr(key):
    color = PALETTE[key]['color'].lstrip('#')
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
    return blue, green, red
