"""Application services shared by HTTP requests and the camera inference loop."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import io
import hashlib
import hmac
import json
import math
from pathlib import Path
import queue
import re
import shutil
import secrets
import threading
import time
import uuid

import numpy as np

from backend.hardware.serial_bridge import SerialBridge
from backend.hardware.gateway_bridge import GatewayBridge
from backend.hardware.uno_protocol import CAPABILITIES, COLOR, DEVICE_BOARDS, PIN
from backend.repository import Repository, RepositoryUnavailable, public_command, utcnow
from backend.vision.camera_service import CameraService
from backend.vision.face_service import FaceService
from backend.vision.model_service import ModelService


DEFAULT_SETTINGS = {'temperature_on':30., 'temperature_off':28., 'door_open_seconds':30,
                    'bulb_linkage':True, 'retention_days':7,
                    'smoke_threshold':400.,'rain_threshold':800.}
DEVICES = {'front_door':('入口门','door',{'position':'closed'}),
    'garage_door':('车库门','door',{'position':'closed'}),
    'window_1':('窗户','window',{'position':'closed'}),
    'main_light':('主灯','light',{'power':False,'brightness':0}),
    'exhaust_fan':('风扇','fan',{'power':False})}


def decode_image(raw):
    if not raw or len(raw) > 8*1024*1024:
        raise ValueError('图片必须非空且不超过8 MB')
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as check:
            if check.format not in ('JPEG','PNG','WEBP') or check.width*check.height > 20_000_000:
                raise ValueError('仅支持 JPEG/PNG/WebP，图片最多2000万像素')
            check.verify()
    except Exception as exc:
        raise ValueError('无效或不支持的图片，请上传 JPEG/PNG/WebP') from exc
    import cv2
    image = cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('无法解码图片')
    return image


class EventBus:
    def __init__(self):
        self.lock = threading.Lock()
        self.subscribers = set()

    def publish(self, name, payload=None):
        message = {'event_id':uuid.uuid4().hex,'type':name,'occurred_at':utcnow(),'source':'http','payload':payload or {}}
        with self.lock:
            for subscriber in self.subscribers:
                try:
                    subscriber.put_nowait(message)
                except queue.Full:
                    # SSE is a notification channel, snapshots remain the authoritative state.
                    try:
                        subscriber.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        subscriber.put_nowait(message)
                    except queue.Full:
                        pass

    def subscribe(self):
        target = queue.Queue(maxsize=32)
        with self.lock:
            self.subscribers.add(target)
        return target

    def unsubscribe(self, target):
        with self.lock:
            self.subscribers.discard(target)


class Runtime:
    def __init__(self, settings, repository=None):
        self.settings = settings
        self.repository = repository or Repository(settings)
        self.events = EventBus()
        self.models = ModelService(settings)
        self.face = FaceService(settings,self.repository)
        self.camera = CameraService(settings,self.process_frame,self.process_faces)
        self.serial = SerialBridge(settings,self.on_hardware_message)
        self.gateway = GatewayBridge(self)
        self.options = dict(DEFAULT_SETTINGS)
        self.errors = {}
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.database_online = False
        self.last_bulb = 0.
        self.bulb_count = 0
        self.last_recognition = 0.
        self.live = {'frame_id':0,'captured_at':None,'objects':[],'faces':[],
                     'width':0,'height':0,'camera_status':'offline','source':'camera','inference_ms':None}
        self.command_lock = threading.RLock()
        self.hardware_error = ''
        self.face_state = {'frame_id':0,'captured_at':None,'faces':[]}
        self.last_cleanup = 0.
        self.last_face_event = 0.
        self.face_event_key = None
        self.last_accelerator_health = 0.
        self._pin_retry_key = secrets.token_bytes(32)

    def start(self):
        self.settings.data_dir.mkdir(parents=True,exist_ok=True)
        for name in ('captures','temporary','faces','features'):
            (self.settings.data_dir/name).mkdir(exist_ok=True)
        try:
            if self.settings.database_init:
                self.repository.initialize()
            self.repository.ping()
            self.options.update(self.repository.get_settings())
            self.database_online = True
            if self.settings.hardware_mode == 'mock':
                if not self.repository.devices():
                    for device_id,(name,kind,state) in DEVICES.items():
                        self.repository.update_device(device_id,name,kind,state,'mock')
                    self.repository.update_device('thermometer_1','模拟温湿度','sensor',{'temperature':26.,'humidity':45.},'mock')
        except Exception as exc:
            self.errors['database'] = str(exc)
        self.models.initialize()
        self.face.initialize()
        if self.settings.auto_bootstrap_faces and self.face.status == 'online':
            self.bootstrap_people()
        if self.settings.hardware_mode == 'serial':
            self.serial.start()
        self.camera.start()
        self.thread = threading.Thread(target=self._maintenance,daemon=True,name='system-maintenance')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.camera.stop()
        self.serial.stop()
        self.gateway.stop()
        if self.thread:
            self.thread.join(timeout=5)
        self.models.close()

    def bootstrap_people(self):
        # Disabled records are tombstones: startup must never restore revoked access.
        known = self.repository.list_people(include_inactive=True)
        names = {p['name'] for p in known} | {p['user_id'] for p in known}
        for path in self.settings.bootstrap_faces_dir.glob('*'):
            if path.suffix.lower() not in ('.jpg','.jpeg','.png') or path.stem in names:
                continue
            try:
                self.register_person(path.stem,path.stem,path.read_bytes())
            except Exception as exc:
                self.errors['bootstrap'] = f'注册交付照片失败: {exc}'

    def status(self):
        self.camera.refresh_health()
        try:
            self.repository.ping()
            self.database_online = True
            self.errors.pop('database',None)
        except Exception as exc:
            self.database_online = False
            self.errors['database'] = str(exc)
        hardware = 'online' if (self.settings.hardware_mode=='mock'
            or self.settings.hardware_mode=='serial' and self.serial.online
            or self.settings.hardware_mode=='gateway' and self.gateway.online) else 'offline'
        label = {'mock': '硬件模式: mock（模拟回执）', 'serial': 'Arduino 实机串口模式',
                 'gateway': '双UNO电脑USB网关；门位置为舵机控制状态，无到位传感器'}
        messages = [label.get(self.settings.hardware_mode, '硬件控制已禁用'),self.camera.message]
        messages.extend(self.errors.values())
        return {'mode':'http','version':'2.0.0','backend':'online','database':'online' if self.database_online else 'offline',
            'camera':self.camera.status,'hardware':hardware,'hardware_mode':self.settings.hardware_mode,
            'model':', '.join(s['name']+':'+s['status'] for s in self.models.states),
            'face_model':self.face.status,'server_time':utcnow(),'message':'；'.join(messages),
            'input_mode':'replay' if self.camera.replay else 'live',
            'hardware_boards':self.gateway.details() if self.settings.hardware_mode=='gateway' else {}}

    def dashboard(self):
        rows = self.repository.devices()
        devices, sensors = [],[]
        now = datetime.now(timezone.utc)
        for row in rows:
            if self.settings.hardware_mode=='gateway' and (row['source']!='gateway' or row['device_id'] not in DEVICE_BOARDS):
                continue
            stamp = datetime.fromisoformat(row['updated_at'].replace('Z','+00:00'))
            online = (row['source']=='mock' and self.settings.hardware_mode=='mock'
                or row['source']=='serial' and self.settings.hardware_mode=='serial' and self.serial.online and (now-stamp).total_seconds()<15
                or row['source']=='gateway' and self.settings.hardware_mode=='gateway' and self.gateway.device_online(row['device_id']) and (now-stamp).total_seconds()<15)
            row['status'] = 'online' if online else 'offline'
            if row['source']=='gateway':
                row['board_id'] = DEVICE_BOARDS.get(row['device_id'])
                row['capabilities'] = CAPABILITIES.get(row['device_id'], [])
            if row['kind']=='sensor':
                for metric,value in row['state'].items():
                    if self.settings.hardware_mode=='gateway' and metric not in ('temperature','humidity','light'):
                        continue
                    measured = row.get('metric_measured_at',{}).get(metric)
                    sample_fresh = bool(measured and (now-datetime.fromisoformat(measured.replace('Z','+00:00'))).total_seconds()<15)
                    sensors.append({'id':row['device_id']+'.'+metric,'device_id':row['device_id'],'metric':metric,
                        'value':value,'unit':'°C' if metric=='temperature' else '%' if metric=='humidity' else 'raw',
                        'measured_at':measured or row['updated_at'],
                        'status':'online' if online and (sample_fresh or self.settings.hardware_mode=='mock')
                            and (self.settings.hardware_mode!='gateway' or self.gateway.sensor_valid(metric)) else 'offline','source':row['source']})
            else:
                devices.append(row)
        return {'freshness':'mock' if self.settings.hardware_mode=='mock' else 'live','server_time':utcnow(),
            'sensors':sensors,'devices':devices,'recent_events':self.repository.events('device',page_size=5)['items']}

    def register_person(self, user_id, name, raw):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',user_id):
            raise ValueError('人员编号只允许1~64位字母、数字、下划线或连字符')
        name = name.strip()
        if not name or len(name)>50:
            raise ValueError('姓名长度应为1~50个字符')
        image = decode_image(raw)
        encoding = self.face.encode_registration(image)
        uid = uuid.uuid4().hex
        feature = self.settings.data_dir/'features'/f'{uid}.npy'
        avatar = self.save_image(image,'faces')
        np.save(feature,encoding,allow_pickle=False)
        try:
            person = self.repository.add_person(user_id,name,feature.resolve(),avatar)
        except Exception:
            feature.unlink(missing_ok=True)
            (self.settings.data_dir/avatar.removeprefix('/uploads/')).unlink(missing_ok=True)
            raise
        self.face.reload()
        self.events.publish('system.status.changed')
        return person

    def remove_person(self, user_id):
        self.repository.delete_person(user_id)
        self.face.reload()
        self.events.publish('system.status.changed')

    def save_image(self, image, folder='captures'):
        import cv2
        target = self.settings.data_dir/folder/f'{uuid.uuid4().hex}.jpg'
        if not cv2.imwrite(str(target),image):
            raise OSError('照片写入失败')
        return '/uploads/'+folder+'/'+target.name

    def snapshot(self):
        frame,frame_id,captured = self.camera.snapshot()
        url = self.save_image(frame)
        return {'camera_id':'camera_0','frame_id':frame_id,'image_url':url,'archive_url':url,
                'saved':True,'captured_at':captured,'status':'online','message':'照片已保存至设备本地'}

    def detect_photo(self, image, source='upload'):
        detections,elapsed = self.models.detect(image)
        url = self.save_image(image)
        payload = {'type':'object','source':source,'image_url':url,'file_name':url.rsplit('/',1)[1],
            'result_summary':f'检测到 {len(detections)} 个目标','detections':detections}
        event = self.repository.event('recognition',payload)
        self.events.publish('recognition.created',{'event_id':event['event_id']})
        return {**event,'width':image.shape[1],'height':image.shape[0],'count':len(detections),
                'inference_ms':elapsed,'mode':'http','message':'真实模型识别；照片不触发硬件联动'}

    def verify_photo(self, image):
        faces = self.face.analyze(image,live=False)
        best = faces[0] if len(faces)==1 else {'matched':False,'identity_matched':False,'similarity':0.,
            'user_id':None,'user_name':'未检测到单个人脸','liveness_status':'unavailable','access_granted':False,
            'reason':'请上传仅包含一人的清晰照片'}
        url = self.save_image(image)
        payload = {'type':'face','source':'upload','image_url':url,'file_name':url.rsplit('/',1)[1],
            'result_summary':best['reason'],'detections':[],**best}
        event = self.repository.event('recognition',payload)
        self.events.publish('recognition.created',{'event_id':event['event_id']})
        return {**event,'face_boxes':[f['bbox'] for f in faces],'mode':'http','message':best['reason'],'command_id':None}

    def process_frame(self, frame, frame_id, captured, live_input, *, captured_monotonic=None, generation=None):
        import cv2
        start = time.monotonic()
        objects = []
        try:
            objects,_ = self.models.detect(frame)
            self.errors.pop('objects',None)
        except Exception as exc:
            self.errors['objects'] = str(exc)
        with self.lock:
            face_state = self.face_state
        # Face inference has its own cadence. Never draw boxes from another frame onto this JPEG.
        if face_state['frame_id'] == frame_id:
            for face in face_state['faces']:
                left,top,right,bottom = face['bbox']
                color = (0,200,0) if face['access_granted'] else (0,160,255)
                cv2.rectangle(frame,(left,top),(right,bottom),color,2)
                cv2.putText(frame,'PASS' if face['access_granted'] else 'WAIT / DENY',(left,max(15,top-5)),cv2.FONT_HERSHEY_SIMPLEX,.5,color,1)
        for obj in objects:
            left,top,right,bottom = obj['bbox']
            cv2.rectangle(frame,(left,top),(right,bottom),(255,150,0),2)
            cv2.putText(frame,f"{obj['label']} {obj['confidence']:.2f}",(left,max(15,top-5)),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,150,0),1)
        if not live_input:
            cv2.putText(frame,'REPLAY: NO ACCESS GRANTS',(10,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(0,0,255),2)
        with self.lock:
            self.live = {'frame_id':frame_id,'captured_at':captured,'objects':objects,'detections':objects,'faces':face_state['faces'],
                'face_frame_id':face_state['frame_id'],'face_captured_at':face_state['captured_at'],
                'width':frame.shape[1],'height':frame.shape[0],'camera_status':self.camera.status,
                'source':'camera' if live_input else 'replay','inference_ms':round((time.monotonic()-start)*1000,1)}
        now = time.monotonic()
        if objects and now-self.last_recognition>10:
            try:
                self.record_live_event(frame,objects,None)
                self.last_recognition = now
            except Exception as exc:
                self.errors['archive'] = str(exc)
        bulb = any(d['label'] in ('bulb','light_bulb','lightbulb') for d in objects)
        trusted = live_input and self.camera.is_current_capture(captured_monotonic,generation)
        self.bulb_count = self.bulb_count+1 if bulb and trusted else 0
        if self.options['bulb_linkage'] and self.bulb_count>=3 and now-self.last_bulb>10:
            try:
                self.send_command('main_light','set',{'power':True,'brightness':80},source='bulb',
                    capture=(captured_monotonic,generation))
                self.last_bulb = now
            except Exception as exc:
                self.errors['bulb'] = str(exc)
        return frame

    def process_faces(self, frame, frame_id, captured, live_input, *, captured_monotonic=None, generation=None):
        if live_input and not self.camera.is_current_capture(captured_monotonic,generation):
            frame = None
        if frame is None:
            self.face.reset_session()
            self.face_event_key = None
            with self.lock:
                self.face_state = {'frame_id':frame_id,'captured_at':captured,'faces':[]}
            return
        try:
            faces = self.face.analyze(frame,live=live_input)
            self.errors.pop('faces',None)
        except Exception as exc:
            self.face.reset_session()
            self.errors['faces'] = str(exc)
            faces = []
        if live_input and not self.camera.is_current_capture(captured_monotonic,generation):
            self.face.reset_session()
            faces = []
        for face in faces:
            if face.get('new_grant') and live_input:
                try:
                    if not self.repository.is_authorized(face['user_id']):
                        raise ValueError('授权已被停用')
                    # DB validation can block; re-check the capture immediately before dispatch.
                    command = self.send_command('front_door','set',{'position':'open'},source='face',
                        capture=(captured_monotonic,generation))
                    face['command_id'] = command['command_id']
                    self.face.remember_command(face['user_id'],command['command_id'])
                    if command['status']=='failed':
                        face['reason'] += '；控制器执行失败: '+str(command.get('error_message',''))
                    self.record_live_event(frame,[],face)
                except Exception as exc:
                    face.update(access_granted=False,liveness_status='failed',reason=f'无法提交门禁: {exc}')
                    self.face.reset_session()
        key = tuple((f.get('user_id'),f.get('liveness_status')) for f in faces)
        if faces and (key!=self.face_event_key or time.monotonic()-self.last_face_event>10):
            try:
                for face in faces:
                    if not face.get('new_grant'):
                        self.record_live_event(frame,[],face)
                self.face_event_key,self.last_face_event = key,time.monotonic()
                self.errors.pop('face_archive',None)
            except Exception as exc:
                self.errors['face_archive'] = f'人脸事件归档失败: {exc}'
        elif not faces:
            self.face_event_key = None
        with self.lock:
            self.face_state = {'frame_id':frame_id,'captured_at':captured,'faces':faces}

    def record_live_event(self, image, objects, face):
        url = self.save_image(image)
        payload = {'type':'face' if face else 'object','source':'camera' if not self.camera.replay else 'replay',
            'image_url':url,'file_name':url.rsplit('/',1)[1],'detections':objects,
            'result_summary':face['reason'] if face else f'检测到{len(objects)}个目标'}
        if face:
            payload.update(face)
        event = self.repository.event('recognition',payload)
        self.events.publish('recognition.created',{'event_id':event['event_id']})

    def send_command(self, device_id, action, params, key=None, source='gui', capture=None):
        if device_id not in DEVICES:
            raise ValueError('不支持的设备编号')
        _,kind,_ = DEVICES[device_id]
        params = self.validate_command(kind,action,params,allow_mode=self.settings.hardware_mode=='gateway')
        with self.command_lock:
            payload = {'device_id':device_id,'action':action,'params':params}
            if 'pin' in params:
                # A four-digit PIN must never be stored as plaintext or as a
                # brute-forceable unkeyed hash. Retry equality is process-local.
                fingerprint = hmac.new(self._pin_retry_key,
                    (device_id+'\0'+params['pin']).encode('ascii'), hashlib.sha256).hexdigest()
                payload = {**payload, 'params': {'pin': '[redacted]'},
                           '_sensitive_fingerprint': fingerprint}
            command,created = self.repository.create_command(device_id,payload,self.settings.hardware_mode,key)
            command = public_command(command)
            if not created:
                return command
            try:
                if capture is not None and not self.camera.is_current_capture(*capture):
                    raise RuntimeError('摄像头会话已变化或当前图像已过期，取消硬件联动')
                if self.settings.hardware_mode=='mock':
                    devices = {d['device_id']:d for d in self.repository.devices()}
                    state = dict(devices.get(device_id,{}).get('state',{}))
                    if action=='toggle':
                        if kind in ('door','window'):
                            state['position'] = 'closed' if state.get('position')=='open' else 'open'
                        else:
                            state['power'] = not state.get('power',False)
                    else:
                        state.update(params)
                    name,_,_ = DEVICES[device_id]
                    self.repository.update_device(device_id,name,kind,state,'mock')
                    command = self.repository.finish_command(command['command_id'],'acked')
                    self.device_event(device_id,state,source,command['command_id'])
                elif self.settings.hardware_mode=='serial':
                    # Serialize final validation with camera invalidation; do not hold
                    # this lock across database operations, which can take seconds.
                    with self.camera.lock:
                        if capture is not None and not self.camera.is_current_capture(*capture):
                            raise RuntimeError('摄像头会话已变化或当前图像已过期，取消硬件联动')
                        self.serial.send(command)
                elif self.settings.hardware_mode=='gateway':
                    self.gateway.send({**command, 'params': params},capture=capture)
                else:
                    raise RuntimeError('硬件控制已禁用')
            except Exception as exc:
                error = '门禁密码修改未能提交，请检查UNO连接及协议' if 'pin' in params else str(exc)
                command = public_command(self.repository.finish_command(command['command_id'],'failed',error))
            self.events.publish('command.updated',command)
            return command

    @staticmethod
    def validate_command(kind, action, params, *, allow_mode=False):
        if action not in ('set','toggle'):
            raise ValueError('action 必须为 set 或 toggle')
        if not isinstance(params,dict):
            raise ValueError('params 必须是对象')
        allowed = {'position'} if kind in ('door','window') else {'power','brightness'} if kind=='light' else {'power'}
        if allow_mode and kind in ('light','fan'):
            allowed = allowed | {'mode'}
        if allow_mode:
            allowed |= {'color','led_count'} if kind=='light' else {'speed'} if kind=='fan' else {'pin'} if kind=='door' else set()
        if set(params)-allowed:
            raise ValueError('设备参数不受支持')
        if action=='set' and not params:
            raise ValueError('set 命令必须提供参数')
        if action=='toggle' and params:
            raise ValueError('toggle不接受参数')
        if 'position' in params and params['position'] not in ('open','closed'):
            raise ValueError('position 必须为 open 或 closed')
        if 'power' in params and not isinstance(params['power'],bool):
            raise ValueError('power 必须是布尔值')
        if 'brightness' in params and (type(params['brightness']) is not int or not 0<=params['brightness']<=100):
            raise ValueError('brightness 必须为0~100整数')
        if 'speed' in params and (type(params['speed']) is not int or not 0<=params['speed']<=100):
            raise ValueError('speed必须为0~100整数')
        if 'led_count' in params and (type(params['led_count']) is not int or not 1<=params['led_count']<=8):
            raise ValueError('led_count必须为1~8整数')
        if 'color' in params and (not isinstance(params['color'],str) or not COLOR.fullmatch(params['color'])):
            raise ValueError('color必须为#RRGGBB颜色')
        if 'pin' in params and (not isinstance(params['pin'],str) or not PIN.fullmatch(params['pin'])):
            raise ValueError('门禁密码必须为4位数字')
        special = set(params) & {'pin','speed','color','led_count'}
        if special and not (set(params)=={'pin'} or set(params)=={'speed'} or set(params)<={'color','led_count'}):
            raise ValueError('调速、颜色/灯珠数、密码修改必须分别下发')
        if 'mode' in params:
            if not isinstance(params['mode'],str) or params['mode'] not in ('auto','manual'):
                raise ValueError('mode必须为auto或manual')
            if action!='set' or params['mode']=='auto' and set(params)!={'mode'}:
                raise ValueError('自动模式必须使用单独的set mode命令')
        return params

    def device_event(self, device_id, state, source, command_id=None):
        name = DEVICES.get(device_id,(device_id,))[0]
        event = self.repository.event('device',{'device_id':device_id,'device_name':name,'action':'set',
            'state':state,'source':source,'command_id':command_id},device_id)
        self.events.publish('device.state.changed',event)

    def on_hardware_message(self, message):
        if message['type']=='heartbeat':
            return
        if message['type']=='ack':
            if message.get('status') not in ('acked','failed'):
                raise ValueError('无效ack状态')
            # ACK only confirms controller execution; physical state requires separate telemetry.
            command = self.repository.finish_command(str(message.get('command_id','')),message['status'],message.get('error'))
            self.events.publish('command.updated',command)
            return
        self.ingest_telemetry(message,'serial')

    def on_gateway_message(self, message):
        if message['type']=='ack':
            command = self.repository.finish_command(message['command_id'],message['status'],message.get('error'))
            self.events.publish('command.updated',command)
        elif message['type']=='local_event':
            device_id = 'front_door' if message['board_id']=='uno1' else 'garage_door'
            if message['event']=='voice':
                device_id = {1:'exhaust_fan',2:'exhaust_fan',3:'main_light',4:'main_light'}.get(message.get('command'),'front_door')
            event = self.repository.event('device',{'device_id':device_id,'device_name':DEVICES[device_id][0],
                'action':message['event'],'state':{},'source':'gateway.'+message['board_id'],
                'local_event':message['event'],
                **{key:message[key] for key in ('command',) if key in message}},device_id)
            self.events.publish('device.state.changed',event)
        else:
            self.ingest_telemetry(message,'gateway')

    def ingest_telemetry(self, message, source='mock'):
        device_id = message.get('device_id')
        state = message.get('state',{})
        if device_id=='thermometer_1':
            if not isinstance(state,dict) or not state or set(state)-{'temperature','humidity','smoke','rain','light'}:
                raise ValueError('无效传感器数据')
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in state.values()):
                raise ValueError('传感器值必须为有限数值')
            limits = {'temperature':(-40,125),'humidity':(0,100),'smoke':(0,1023),'rain':(0,1023),'light':(0,1023)}
            if any(not limits[k][0]<=v<=limits[k][1] for k,v in state.items()):
                raise ValueError('传感器值超出有效范围')
            name,kind = '温湿度／环境传感器','sensor'
        elif device_id in DEVICES:
            name,kind,_ = DEVICES[device_id]
            if source=='gateway':
                if not isinstance(state,dict):
                    raise ValueError('无效网关设备状态')
                controls = {k:v for k,v in state.items() if k not in ('mode','state_basis')}
                if 'mode' in state and (kind not in ('light','fan') or state['mode'] not in ('auto','manual')):
                    raise ValueError('无效设备自动模式')
                if 'state_basis' in state and (kind!='door' or state['state_basis']!='actuator'):
                    raise ValueError('无效设备状态依据')
                if device_id=='garage_door' and controls=={'position':'moving'}:
                    pass
                else:
                    # State reports contain all fields together; a command only
                    # accepts combinations implemented atomically on the wire.
                    if 'pin' in controls:
                        raise ValueError('硬件状态不能包含门禁密码')
                    for key,value in controls.items():
                        self.validate_command(kind,'set',{key:value},allow_mode=True)
            else:
                self.validate_command(kind,'set',state)
        else:
            raise ValueError('未知设备编号')
        self.repository.update_device(device_id,name,kind,state,source)
        self.device_event(device_id,state,source)
        self.events.publish('sensor.updated' if kind=='sensor' else 'device.state.changed')
        if kind=='sensor' and 'temperature' in state:
            value = state['temperature']
            self.repository.alert('temperature.high',f'温度过高: {value} °C',active=value>=self.options['temperature_on'])
            # UNO1 owns its local hysteresis and manual/voice modes. Gateway
            # telemetry must never force FAN_ON/OFF and steal that ownership.
            if self.settings.hardware_mode!='gateway':
                fan = next((d for d in self.repository.devices() if d['device_id']=='exhaust_fan'),None)
                power = fan['state'].get('power') if fan else None
                if value>=self.options['temperature_on'] and power is not True:
                    self.send_command('exhaust_fan','set',{'power':True},source='temperature')
                elif value<=self.options['temperature_off'] and power is True:
                    self.send_command('exhaust_fan','set',{'power':False},source='temperature')
        if kind=='sensor' and 'smoke' in state:
            self.repository.alert('smoke.detected','烟雾传感器触发报警（请以硬件校准阈值为准）',severity='critical',active=state['smoke']>=self.options['smoke_threshold'])
        if kind=='sensor' and 'rain' in state:
            rainy = state['rain']>=self.options['rain_threshold']
            self.repository.alert('rain.detected','检测到雨滴，请确认窗户状态',active=rainy)
            if rainy:
                self.send_command('window_1','set',{'position':'closed'},source='rain')

    def update_options(self, values):
        if set(values)-set(DEFAULT_SETTINGS):
            raise ValueError('包含不支持的设置项')
        result = {**self.options,**values}
        if any(type(result[k]) not in (int,float) or not math.isfinite(result[k]) for k in ('temperature_on','temperature_off','door_open_seconds','retention_days','smoke_threshold','rain_threshold')):
            raise ValueError('阈值必须为有限数字')
        if not -20<=result['temperature_off']<result['temperature_on']<=80:
            raise ValueError('温控关闭阈值应小于开启阈值，且在-20~80°C内')
        if self.settings.hardware_mode=='gateway' and any(
                abs(result[key]*10-round(result[key]*10))>1e-6 for key in ('temperature_on','temperature_off')):
            raise ValueError('UNO温控阈值最多保留1位小数（0.1°C）')
        if not 5<=result['door_open_seconds']<=3600 or not 1<=result['retention_days']<=365:
            raise ValueError('门未关阈值应在5~3600秒，保存时间应在1~365天')
        if not isinstance(result['bulb_linkage'],bool):
            raise ValueError('bulb_linkage 必须是布尔值')
        if not 0<=result['smoke_threshold']<=1023 or not 0<=result['rain_threshold']<=1023:
            raise ValueError('烟雾和雨滴原始值阈值应在0~1023内，接实机前应校准')
        self.repository.save_settings(result)
        self.options = result
        self.events.publish('system.status.changed')
        return result

    def _maintenance(self):
        while not self.stop_event.wait(5):
            try:
                self.repository.ping()
                self.camera.refresh_health()
                self.database_online = True
                self.errors.pop('database',None)
                if self.face.library is not None and self.face.predictor is not None and self.face.status!='online':
                    self.face.reload()
                    self.face.status,self.face.message = 'online','人脸模型已恢复'
                self.repository.expire_commands()
                self.repository.alert('camera.offline',self.camera.message,active=self.camera.status!='online')
                self.repository.alert('hardware.offline','Arduino 心跳超时或未连接',active=(self.settings.hardware_mode=='serial' and not self.serial.online)
                    or (self.settings.hardware_mode=='gateway' and not self.gateway.online))
                if self.settings.hardware_mode=='gateway':
                    self.check_gateway_alerts()
                self.repository.alert('face.offline',self.face.message,active=self.face.status!='online')
                for model in self.models.states:
                    self.repository.alert('model.'+model['name'],model['message'],active=model['status']!='online')
                if time.monotonic()-self.last_accelerator_health>60:
                    health = self.models.accelerator_health()
                    if health is not None:
                        active,message = health
                        self.repository.alert('npu.health',message,active=active)
                    self.last_accelerator_health = time.monotonic()
                self.repository.alert('storage.low','剩余磁盘空间不足1 GB',active=shutil.disk_usage(self.settings.data_dir).free<1024**3)
                self.check_door_alerts()
                self.events.publish('system.status.changed')
                if time.monotonic()-self.last_cleanup>1800:
                    self.prune_archives()
                    self.last_cleanup = time.monotonic()
            except Exception as exc:
                self.database_online = False
                self.errors['database'] = str(exc)
                self.face.reset_session()

    def check_gateway_alerts(self):
        details = self.gateway.details()
        for board,detail in details.items():
            self.repository.alert('hardware.'+board+'.offline',board.upper()+' USB状态未更新',active=detail['status']!='online')
        self.repository.alert('sensor.dht.failed','UNO1温湿度传感器读取失败',
            active=details['uno1']['status']=='online' and details['uno1'].get('dht_ok') is False)
        uno2 = details['uno2']
        online = uno2['status']=='online'
        self.repository.alert('sensor.rfid.failed','UNO2 RFID读卡器通信异常',
            active=online and uno2.get('rfid_ok') is False)
        # The selected policy accepts readable cards; resolve old whitelist alarms.
        self.repository.alert('security.rfid.unrestricted','RFID使用有效卡通行策略', active=False)

    def check_door_alerts(self):
        for device in self.repository.devices():
            if self.settings.hardware_mode=='gateway' and (device.get('source')!='gateway'
                    or device['device_id'] not in DEVICE_BOARDS):
                continue
            if device['kind']=='door':
                since = datetime.fromisoformat((device.get('open_since') or device['updated_at']).replace('Z','+00:00'))
                active = device['state'].get('position')=='open' and (datetime.now(timezone.utc)-since).total_seconds()>self.options['door_open_seconds']
                self.repository.alert('door.open.'+device['device_id'],'门长时间未关闭',active=active)

    def prune_archives(self):
        cutoff = datetime.now(timezone.utc)-timedelta(days=self.options['retention_days'])
        self.repository.prune_recognition(cutoff.replace(tzinfo=None))
        # Only aged capture/temp JPG files are eligible; registered faces/features remain intact.
        for folder in ('captures','temporary'):
            for path in (self.settings.data_dir/folder).glob('*.jpg'):
                if path.is_file() and not path.is_symlink() and path.stat().st_mtime<cutoff.timestamp():
                    path.unlink()

    def clear_temporary(self):
        count = 0
        for path in (self.settings.data_dir/'temporary').glob('*.jpg'):
            if path.is_file() and not path.is_symlink():
                path.unlink()
                count += 1
        return {'count':count}
