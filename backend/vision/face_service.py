"""Identity matching and bounded, single-person live blink sessions."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import numpy as np


def _inference_rgb(image):
    """Bound HOG work while retaining scale factors for original-image boxes."""
    height, width = image.shape[:2]
    if max(height, width) > 800:
        import cv2
        ratio = 800 / max(height, width)
        image = cv2.resize(image, (max(1, round(width * ratio)), max(1, round(height * ratio))),
                           interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(image[:, :, ::-1]), width / image.shape[1], height / image.shape[0]


class FaceSession:
    def __init__(self, threshold=.23, closed_frames=2, timeout=12., max_gap=1.5):
        self.threshold, self.closed_frames = threshold, closed_frames
        self.timeout, self.max_gap = timeout, max_gap
        self.reset()

    def reset(self):
        self.identity = None
        self.started = self.last_seen = 0.
        self.closed = 0
        self.saw_open = False
        self.passed = False
        self.command_id = None

    def observe(self, identity, ear, *, face_count=1, now=None, live=True):
        now = time.monotonic() if now is None else now
        if not live:
            return self.result(identity, 'unavailable', False, False, '静态照片或录像只能匹配身份，不能验证现场眨眼')
        if face_count != 1 or not identity or ear is None:
            self.reset()
            reason = '请保持画面中只有一人' if face_count > 1 else '未检测到稳定的授权人脸'
            return self.result(identity, 'pending', False, False, reason)
        if identity != self.identity or now - self.last_seen > self.max_gap or now - self.started > self.timeout:
            self.reset()
            self.identity, self.started = identity, now
        self.last_seen = now
        new_grant = False
        if ear >= self.threshold:
            if self.saw_open and self.closed >= self.closed_frames and not self.passed:
                self.passed, new_grant = True, True
            self.saw_open, self.closed = True, 0
        elif self.saw_open:
            self.closed += 1
        result = self.result(identity, 'passed' if self.passed else 'pending', self.passed, new_grant,
                             '当前会话已完成眨眼' if self.passed else '身份已匹配，请眨眼验证')
        result['command_id'] = self.command_id
        return result

    @staticmethod
    def result(identity, status, granted, new_grant, reason):
        return {'identity_matched': bool(identity), 'matched': bool(identity), 'user_id': identity,
                'liveness_status': status, 'access_granted': granted, 'new_grant': new_grant, 'reason': reason}


class FaceService:
    def __init__(self, settings, repository):
        self.settings, self.repository = settings, repository
        self.session = FaceSession()
        self.lock = threading.RLock()
        # face_recognition shares native HOG/encoder objects across callers.
        self.inference_lock = threading.Lock()
        self.status, self.message = 'unknown', '人脸模型尚未初始化'
        self.library = self.predictor = None
        self.people = []
        self.last_bbox = None

    def initialize(self):
        if not self.settings.face_enabled:
            self.status, self.message = 'offline', '人脸识别已禁用'
            return
        try:
            import face_recognition
            import dlib
            self.library = face_recognition
            self.predictor = dlib.shape_predictor(str(self.settings.face_predictor))
            self.reload()
            self.status, self.message = 'online', '人脸与68点关键点模型可用'
        except (Exception,SystemExit) as exc:
            self.status, self.message = 'offline', f'人脸模型不可用: {exc}'

    def reload(self):
        people = self.repository.list_people(include_features=True)
        valid = []
        for p in people:
            feature = p.get('face_feature_path')
            if feature and Path(feature).suffix.lower()=='.npy' and Path(feature).exists():
                encoding = np.load(feature, allow_pickle=False)
                if encoding.shape == (128,) and np.isfinite(encoding).all():
                    valid.append((p, encoding))
        with self.lock:
            self.people = valid
            self.session.reset()

    def reset_session(self):
        with self.lock:
            self.session.reset()
            self.last_bbox = None

    def remember_command(self, identity, command_id):
        with self.lock:
            if self.session.identity == identity and self.session.passed:
                self.session.command_id = command_id

    def encode_registration(self, image):
        with self.inference_lock:
            return self._encode_registration(image)

    def _encode_registration(self, image):
        if self.library is None:
            raise RuntimeError(self.message)
        rgb, _, _ = _inference_rgb(image)
        boxes = self.library.face_locations(rgb, model='hog')
        if len(boxes) != 1:
            raise ValueError('注册照片必须包含且仅包含一张清晰人脸')
        encodings = self.library.face_encodings(rgb, boxes)
        if not encodings:
            raise ValueError('照片无法提取人脸特征')
        return encodings[0]

    def analyze(self, image, *, live=False):
        with self.inference_lock:
            return self._analyze(image, live=live)

    def _analyze(self, image, *, live=False):
        if self.library is None or self.predictor is None:
            raise RuntimeError(self.message)
        import dlib
        rgb, scale_x, scale_y = _inference_rgb(image)
        boxes = self.library.face_locations(rgb, model='hog')
        encodings = self.library.face_encodings(rgb, boxes)
        faces = []
        with self.lock:
            if not boxes:
                if live:
                    self.session.reset()
                self.last_bbox = None
            for (top, right, bottom, left), encoding in zip(boxes, encodings):
                person, distance = None, 1.
                if self.people:
                    distances = self.library.face_distance([e for _, e in self.people], encoding)
                    index = int(np.argmin(distances))
                    distance = float(distances[index])
                    if distance < self.settings.face_tolerance:
                        person = self.people[index][0]
                ear = None
                if live and len(boxes) == 1:
                    current = (left, top, right, bottom)
                    if self.last_bbox and _iou(current, self.last_bbox) < .15:
                        self.session.reset()
                    self.last_bbox = current
                    shape = self.predictor(rgb, dlib.rectangle(left, top, right, bottom))
                    points = np.array([[shape.part(i).x, shape.part(i).y] for i in range(68)])
                    ear = (_ear(points[36:42]) + _ear(points[42:48])) / 2
                result = self.session.observe(person['user_id'] if person else None, ear,
                                              face_count=len(boxes), live=live)
                result.update(user_name=person['name'] if person else '未授权人员',
                              similarity=max(0., 1. - distance),
                              bbox=[round(left * scale_x), round(top * scale_y),
                                    round(right * scale_x), round(bottom * scale_y)],
                              ear=ear)
                result.setdefault('command_id',None)
                faces.append(result)
        return faces


def _ear(points):
    width = np.linalg.norm(points[0] - points[3])
    return float((np.linalg.norm(points[1] - points[5]) + np.linalg.norm(points[2] - points[4])) / (2 * width)) if width else 0.


def _iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union else 0.
