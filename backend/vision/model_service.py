"""Thread-safe custom and COCO model inference, with explicit load failures."""
import threading
import time
import subprocess
import math
import numpy as np
from pathlib import Path


LABELS = {'drone':'无人机','fire_extinguisher':'灭火器','bulb':'灯泡','light_bulb':'灯泡','lightbulb':'灯泡',
          'person':'人','car':'汽车','truck':'卡车','bus':'公交车','bicycle':'自行车','motorcycle':'摩托车',
          'chair':'椅子','bottle':'瓶子','cat':'猫','dog':'狗','cell phone':'手机','laptop':'笔记本电脑'}

GENERAL_EXCLUDED_LABELS = frozenset({'airplane', 'drone', 'vase'})


class ModelService:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.Lock()
        self.models = []
        self.states = []

    def initialize(self):
        from pathlib import Path
        for name, path in [('custom', self.settings.custom_model), ('general', self.settings.general_model)]:
            state = {'name':name, 'status':'offline', 'classes':[], 'message':''}
            try:
                if not Path(path).is_file():
                    raise FileNotFoundError(f'未找到 {name} 权重文件')
                if Path(path).suffix.lower()=='.om':
                    from backend.vision.ascend_service import AscendYolo
                    model = AscendYolo(path)
                    state['backend'] = 'ascend'
                else:
                    from ultralytics import YOLO
                    model = YOLO(str(path))
                    state['backend'] = 'cpu'
                self.models.append((name,model))
                state.update(status='online', classes=list(model.names.values()), message='模型已加载')
            except Exception as exc:
                state['message'] = str(exc)
            self.states.append(state)

    def detect(self, image):
        if not self.models:
            raise RuntimeError('所有物体识别模型均不可用')
        start = time.monotonic()
        detections = []
        successful = 0
        threshold = float(np.float32(self.settings.confidence))
        # Upstream YOLO uses strict >. Include the configured float32 boundary,
        # then enforce the real threshold below without changing model scores.
        entry_threshold = max(0., float(np.nextafter(np.float32(threshold), np.float32(-np.inf))))
        with self.lock:
            for name, model in self.models:
                state = next(s for s in self.states if s['name']==name)
                try:
                    if state.get('backend')=='ascend':
                        native = model.detect(image,self.settings.confidence)
                        results = None
                    else:
                        results = model.predict(image, conf=entry_threshold, imgsz=self.settings.inference_size,
                                                device='cpu', verbose=False)
                        native = []
                        for result in results:
                            for box in result.boxes:
                                native.append({'label':result.names[int(box.cls[0])],'confidence':float(box.conf[0]),
                                    'bbox':[int(x) for x in box.xyxy[0].tolist()]})
                    state.update(status='online',message='模型推理正常')
                    successful += 1
                except Exception as exc:
                    state.update(status='offline',message=f'模型推理失败: {exc}')
                    continue
                for detection in native:
                    if not math.isfinite(detection['confidence']) or detection['confidence'] < threshold:
                        continue
                    label = detection['label']
                    if name == 'general' and label.strip().casefold() in GENERAL_EXCLUDED_LABELS:
                        continue
                    if name == 'general' and any(label in s['classes'] for s in self.states if s['name']=='custom' and s['status']=='online'):
                        continue
                    detections.append({**detection,'label_zh':LABELS.get(label,label),'model':name})
        if not successful:
            raise RuntimeError('所有已加载模型推理失败，请检查模型状态')
        return detections, round((time.monotonic()-start)*1000, 1)

    def close(self):
        with self.lock:
            for _,model in self.models:
                close = getattr(model,'close',None)
                if close:
                    close()

    def accelerator_health(self):
        if not any(state.get('backend')=='ascend' for state in self.states):
            return None
        executable = Path('/usr/local/sbin/npu-smi')
        try:
            result = subprocess.run([str(executable),'info','-t','health','-i','0','-c','0'],
                capture_output=True,text=True,timeout=3,check=True)
            values = dict(line.strip().split(':',1) for line in result.stdout.splitlines() if ':' in line)
            values = {key.strip():value.strip() for key,value in values.items()}
            status = values.get('Health Status',values.get('Health','unknown'))
            if status.lower() in ('ok','healthy','normal'):
                return False,'Ascend 设备健康检查正常'
            return True,f"Ascend 健康状态 {status}，代码 {values.get('Error Code','unknown')}：{values.get('Error Information','请检查板端 npu-smi')}"
        except (OSError,subprocess.SubprocessError) as exc:
            return True,f'无法完成 Ascend 健康检查: {type(exc).__name__}'
