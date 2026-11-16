"""Stable HTTP contract for both the Web GUI and Capacitor client."""
import asyncio
import hmac
import json
import queue

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from backend.repository import RepositoryUnavailable, utcnow
from backend.runtime import decode_image


router = APIRouter(prefix='/api')


def runtime(request: Request):
    return request.app.state.runtime


def has_write_access(request):
    settings = request.app.state.runtime.settings
    if settings.allow_unauthenticated_writes:
        return True
    supplied = request.headers.get('Authorization','')
    return bool(settings.api_token) and hmac.compare_digest(supplied,'Bearer '+settings.api_token)


def require_admin(request: Request):
    if not has_write_access(request):
        raise HTTPException(401,'请在连接设置中填写管理员访问令牌')


def require_gateway(request: Request):
    settings = request.app.state.runtime.settings
    token = settings.gateway_token
    supplied = request.headers.get('Authorization','')
    if not token or not hmac.compare_digest(supplied.encode('utf-8'),('Bearer '+token).encode('utf-8')):
        raise HTTPException(401,'电脑网关令牌无效或尚未配置')
    if settings.hardware_mode!='gateway':
        raise HTTPException(409,'当前未启用双UNO电脑网关模式')


@router.post('/hardware/gateway/exchange',dependencies=[Depends(require_gateway)])
async def gateway_exchange(request: Request,rt=Depends(runtime)):
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 32768:
            raise HTTPException(413,'网关批次超过32KB')
        chunks.append(chunk)
    try:
        payload = json.loads(b''.join(chunks))
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise ValueError('无效网关JSON') from exc
    return await asyncio.to_thread(rt.gateway.exchange,payload)


async def read_image(image):
    data = await image.read(8*1024*1024+1)
    return await asyncio.to_thread(decode_image,data)


@router.get('/auth/status')
def auth_status(request: Request):
    return {'write_access':has_write_access(request),
            'authentication_required':not request.app.state.runtime.settings.allow_unauthenticated_writes}


@router.get('/system/status')
def system_status(rt=Depends(runtime)):
    return rt.status()


@router.get('/dashboard/snapshot')
def dashboard(rt=Depends(runtime)):
    return rt.dashboard()


@router.get('/sensors/history')
def sensor_history(start: str|None=None,end: str|None=None,metric: str|None=None,
                   device_id: str|None=None,rt=Depends(runtime)):
    metrics = [metric] if metric else ['temperature','humidity']
    if any(m not in ('temperature','humidity','smoke','rain','light') for m in metrics):
        raise ValueError('不支持的传感器指标')
    return [rt.repository.sensor_history(m,start,end,device_id) for m in metrics]


@router.get('/devices/events')
def device_events(start: str|None=None,end: str|None=None,device_id: str|None=None,
                  page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=100),rt=Depends(runtime)):
    return rt.repository.events('device',start,end,device_id,page,page_size)


@router.post('/devices/{device_id}/commands',dependencies=[Depends(require_admin)])
def command(device_id: str,body: dict=Body(...),idempotency_key: str|None=Header(None),rt=Depends(runtime)):
    if idempotency_key and len(idempotency_key)>128:
        raise ValueError('幂等键过长')
    return rt.send_command(device_id,body.get('action'),body.get('params',{}),idempotency_key)


@router.get('/commands/{command_id}')
def get_command(command_id: str,rt=Depends(runtime)):
    return rt.repository.command(command_id)


@router.get('/recognition/events')
def recognition_events(start: str|None=None,end: str|None=None,page: int=Query(1,ge=1),
                       page_size: int=Query(20,ge=1,le=100),rt=Depends(runtime)):
    return rt.repository.events('recognition',start,end,page=page,page_size=page_size)


@router.get('/camera/snapshot')
def snapshot(rt=Depends(runtime)):
    return rt.snapshot()


@router.post('/object-detect')
async def objects(image: UploadFile=File(...),source: str=Form('upload'),rt=Depends(runtime)):
    frame = await read_image(image)
    # source is metadata only; uploaded images can never masquerade as trusted live sessions.
    return await asyncio.to_thread(rt.detect_photo,frame,'upload')


@router.post('/face-verify')
async def face_verify(image: UploadFile=File(...),rt=Depends(runtime)):
    return await asyncio.to_thread(rt.verify_photo,await read_image(image))


@router.get('/person/list')
def people(rt=Depends(runtime)):
    return rt.repository.list_people()


@router.post('/person/add',dependencies=[Depends(require_admin)])
async def add_person(name: str=Form(...),user_id: str=Form(...),face_image: UploadFile=File(...),rt=Depends(runtime)):
    raw = await face_image.read(8*1024*1024+1)
    return await asyncio.to_thread(rt.register_person,user_id,name,raw)


@router.delete('/person/delete',dependencies=[Depends(require_admin)])
def delete_person(user_id: str,rt=Depends(runtime)):
    rt.remove_person(user_id)
    return {'deleted':True}


@router.delete('/temp/clear',dependencies=[Depends(require_admin)])
def clear_temporary(rt=Depends(runtime)):
    return rt.clear_temporary()


@router.get('/vision/live')
def live(rt=Depends(runtime)):
    rt.camera.refresh_health()
    with rt.lock:
        result = {**rt.live,'faces':rt.face_state['faces'],'face_frame_id':rt.face_state['frame_id'],
            'face_captured_at':rt.face_state['captured_at'],'camera_status':rt.camera.status,
            'server_time':utcnow(),'message':rt.camera.message}
        if rt.camera.status!='online':
            result.update(objects=[],detections=[],faces=[])
        return result


@router.get('/camera/stream')
async def stream(request: Request,rt=Depends(runtime)):
    rt.camera.refresh_health()
    if rt.camera.status!='online':
        raise HTTPException(503,rt.camera.message)
    async def frames():
        previous = None
        while not await request.is_disconnected():
            with rt.camera.lock:
                jpeg = rt.camera.jpeg
                online = rt.camera.status=='online'
            if not online:
                break
            if jpeg is not None and jpeg is not previous:
                previous = jpeg
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'+jpeg+b'\r\n'
            await asyncio.sleep(.05)
    return StreamingResponse(frames(),media_type='multipart/x-mixed-replace; boundary=frame',
                             headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


@router.get('/stream')
async def events(request: Request,rt=Depends(runtime)):
    subscriber = rt.events.subscribe()
    async def messages():
        try:
            yield ': connected\n\n'
            while not await request.is_disconnected():
                try:
                    message = subscriber.get_nowait()
                    yield 'event: '+message['type']+'\ndata: '+json.dumps(message,ensure_ascii=False)+'\n\n'
                except queue.Empty:
                    await asyncio.sleep(.25)
                    yield ': keepalive\n\n'
        finally:
            rt.events.unsubscribe(subscriber)
    return StreamingResponse(messages(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


@router.get('/alerts')
def alerts(rt=Depends(runtime)):
    return rt.repository.alerts()


@router.post('/alerts/{alert_id}/ack',dependencies=[Depends(require_admin)])
def ack(alert_id: str,rt=Depends(runtime)):
    rt.repository.ack_alert(alert_id)
    return {'acknowledged':True}


@router.get('/models')
def models(rt=Depends(runtime)):
    return {'items':[*rt.models.states,{'name':'face','status':rt.face.status,'classes':['authorized','unknown'],'message':rt.face.message}]}


@router.get('/settings')
def settings(rt=Depends(runtime)):
    return rt.options


@router.put('/settings',dependencies=[Depends(require_admin)])
def update_settings(body: dict=Body(...),rt=Depends(runtime)):
    return rt.update_options(body)


@router.post('/simulation/telemetry',dependencies=[Depends(require_admin)])
def simulate(body: dict=Body(...),rt=Depends(runtime)):
    if rt.settings.hardware_mode!='mock':
        raise HTTPException(409,'实机模式禁止注入模拟传感器数据')
    rt.ingest_telemetry(body,'mock')
    return {'accepted':True,'mode':'mock'}
