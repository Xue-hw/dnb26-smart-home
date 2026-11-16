"""One capture owner and one bounded latest-frame inference consumer."""
from __future__ import annotations

from pathlib import Path
import threading
import time

from backend.repository import utcnow


class CameraService:
    FRAME_TIMEOUT = 5.
    ACTION_FRAME_MAX_AGE = 1.5

    def __init__(self, settings, process_frame, process_face=None):
        self.settings, self.process_frame, self.process_face = settings, process_frame, process_face
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.frame = self.jpeg = None
        self.frame_id, self.captured_at, self.last_frame = 0, None, 0.
        self.generation = 0
        self.status, self.message = 'offline', '摄像头尚未启动'
        self.threads = []
        source = settings.camera_source
        self.replay = not (str(source).isdigit() or str(source).startswith(('/dev/video','rtsp://','rtsps://')))

    def start(self):
        if not self.settings.camera_enabled:
            self.message = '摄像头已禁用，当前没有实时输入'
            return
        self.threads = [threading.Thread(target=self._capture, name='camera-capture', daemon=True),
                        threading.Thread(target=self._infer, name='vision-inference', daemon=True),
                        threading.Thread(target=self._watchdog, name='camera-watchdog', daemon=True)]
        if self.process_face is not None:
            self.threads.append(threading.Thread(target=self._faces, name='face-inference', daemon=True))
        for thread in self.threads:
            thread.start()

    def invalidate(self, message):
        with self.lock:
            self.generation += 1
            self.status, self.message = 'offline', message
            self.frame = self.jpeg = None

    def refresh_health(self):
        with self.lock:
            if self.status == 'online' and time.monotonic()-self.last_frame > self.FRAME_TIMEOUT:
                self.invalidate('摄像头超过5秒未提供新画面')

    def _watchdog(self):
        while not self.stop_event.wait(.1):
            self.refresh_health()

    def is_current_capture(self, captured_monotonic, generation):
        with self.lock:
            if captured_monotonic is None or generation is None or self.replay:
                return False
            now = time.monotonic()
            return (self.status == 'online' and self.frame is not None and generation == self.generation
                    and 0 <= now-captured_monotonic <= self.ACTION_FRAME_MAX_AGE
                    and 0 <= now-self.last_frame <= self.ACTION_FRAME_MAX_AGE)

    def _capture(self):
        import cv2
        source = self.settings.camera_source
        source = int(source) if str(source).isdigit() else source
        while not self.stop_event.is_set():
            cap = None
            try:
                if isinstance(source,str) and source.startswith(('rtsp://','rtsps://')):
                    cap = cv2.VideoCapture(source,cv2.CAP_FFMPEG,
                        [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,3000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,3000])
                else:
                    cap = cv2.VideoCapture(source)
                with self.lock:
                    self.generation += 1
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera_height)
                cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                if not cap.isOpened():
                    raise RuntimeError('无法打开配置的摄像头或录像源')
                fps = cap.get(cv2.CAP_PROP_FPS) or 25
                while not self.stop_event.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        raise RuntimeError('读取图像失败或录像结束')
                    with self.lock:
                        self.frame = frame
                        self.frame_id += 1
                        self.captured_at, self.last_frame = utcnow(), time.monotonic()
                        self.status, self.message = 'online', '录像回放（不允许门禁放行）' if self.replay else '实时摄像头'
                    if self.replay:
                        self.stop_event.wait(1/max(1, min(fps, 60)))
            except Exception as exc:
                self.invalidate(str(exc))
            finally:
                if cap is not None:
                    cap.release()
            self.stop_event.wait(3)

    def _infer(self):
        import cv2
        last_id = -1
        while not self.stop_event.is_set():
            with self.lock:
                frame = self.frame.copy() if self.frame is not None else None
                frame_id, captured = self.frame_id, self.captured_at
                captured_monotonic,generation = self.last_frame,self.generation
            if frame is None or frame_id == last_id:
                self.stop_event.wait(.03)
                continue
            last_id = frame_id
            try:
                annotated = self.process_frame(frame, frame_id, captured, not self.replay,
                    captured_monotonic=captured_monotonic,generation=generation)
                ok, jpeg = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 78])
                if ok:
                    with self.lock:
                        if self.status=='online' and generation==self.generation:
                            self.jpeg = jpeg.tobytes()
            except Exception as exc:
                self.message = f'视觉处理失败: {exc}'
            self.stop_event.wait(self.settings.inference_interval)

    def _faces(self):
        previous = -1
        while not self.stop_event.is_set():
            with self.lock:
                frame = self.frame.copy() if self.frame is not None else None
                frame_id, captured = self.frame_id, self.captured_at
                captured_monotonic,generation = self.last_frame,self.generation
            if frame is None:
                self.process_face(None,frame_id,captured,not self.replay)
                self.stop_event.wait(.1)
                continue
            if frame_id == previous:
                self.stop_event.wait(.02)
                continue
            previous = frame_id
            try:
                self.process_face(frame,frame_id,captured,not self.replay,
                    captured_monotonic=captured_monotonic,generation=generation)
            except Exception as exc:
                self.message = f'人脸处理失败: {exc}'
            self.stop_event.wait(.02)

    def snapshot(self):
        self.refresh_health()
        with self.lock:
            if self.frame is None or self.status != 'online' or time.monotonic()-self.last_frame > 5:
                raise RuntimeError('摄像头离线或没有新画面')
            return self.frame.copy(), self.frame_id, self.captured_at

    def stop(self):
        self.stop_event.set()
        self.invalidate('摄像头已停止')
        for thread in self.threads:
            thread.join(timeout=4)
