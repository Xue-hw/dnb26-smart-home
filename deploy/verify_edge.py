"""Exercise the deployed HTTP API with private credentials kept on the board.

Run with --exercise only while the Arduino adapter is explicitly in mock mode.
The report contains check results, timings and model classes, never credentials.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import httpx


def verify(root: Path, exercise=False):
    checks = {}
    credentials = json.loads((root/'shared/credentials.json').read_text())
    headers = {'Authorization': 'Bearer '+credentials['api_token']}
    with httpx.Client(base_url='http://127.0.0.1:8080', timeout=120) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        status = request('GET', '/api/system/status')
        assert status['database'] == 'online'
        checks['database_online'] = True
        checks['camera'] = status['camera']
        checks['hardware_mode'] = status['hardware_mode']
        checks['server_time'] = status['server_time']
        models = request('GET', '/api/models')['items']
        assert all(m['status']=='online' for m in models)
        checks['models'] = [{k: m.get(k) for k in ('name','status','classes','backend')} for m in models]
        assert client.get('/').status_code == 200
        checks['web_http'] = True
        assert client.put('/api/settings', json={}).status_code == 401
        assert httpx.get('http://127.0.0.1:8000/control').status_code == 410
        assert not request('GET','/api/auth/status')['write_access']
        assert request('GET','/api/auth/status',headers=headers)['write_access']
        checks['write_auth_and_legacy_lockout'] = True
        photos = sorted((root/'current/integrations/face_recognition/photos').glob('*.jpg'))
        people = request('GET','/api/person/list')
        checks['active_people_count'] = len(people)
        matched = 0
        timings = []
        for photo in photos:
            start = time.monotonic()
            with photo.open('rb') as stream:
                result = request('POST','/api/face-verify', files={'image':(photo.name,stream,'image/jpeg')})
            assert result['identity_matched'] and result['user_id']==photo.stem
            assert result['access_granted'] is False and result['command_id'] is None
            matched += 1
            timings.append(round((time.monotonic()-start)*1000,1))
        checks['registered_photo_identity_matches'] = matched
        checks['all_static_faces_denied_access'] = True
        checks['face_photo_ms'] = timings
        from PIL import Image
        import io
        blank = io.BytesIO()
        Image.new('RGB',(320,240),'white').save(blank,format='JPEG')
        result = request('POST','/api/face-verify',files={'image':('blank.jpg',blank.getvalue(),'image/jpeg')})
        assert not result['identity_matched'] and not result['access_granted']
        checks['no_face_denied'] = True
        assert client.post('/api/object-detect',files={'image':('bad.jpg',b'not-an-image','image/jpeg')}).status_code == 400
        checks['invalid_image_rejected'] = True
        # Use a real team photo to exercise both object models and archival.
        with photos[0].open('rb') as stream:
            result = request('POST','/api/object-detect',files={'image':('sample.jpg',stream,'image/jpeg')})
        assert 'detections' in result and result['image_url'].startswith('/uploads/captures/')
        assert client.get(result['image_url']).status_code==200
        checks['object_models_and_saved_capture'] = True
        checks['object_photo_ms'] = result['inference_ms']
        checks['detected_labels'] = sorted({d['label'] for d in result['detections']})
        assert request('GET','/api/recognition/events')['items']
        checks['recognition_history_persisted'] = True
        if status['camera']=='offline':
            assert client.get('/api/camera/snapshot').status_code==503
            assert client.get('/api/camera/stream').status_code==503
            live = request('GET','/api/vision/live')
            assert not live['faces'] and not live.get('objects',[])
            checks['camera_offline_rejects_snapshot_and_clears_live'] = True

        if exercise:
            if status['hardware_mode']!='mock':
                raise RuntimeError('Refusing simulation/control exercise outside explicit mock mode')
            original = request('GET','/api/settings')
            changed = {**original,'temperature_on':32,'temperature_off':28}
            request('PUT','/api/settings',json=changed,headers=headers)
            try:
                def telemetry(state):
                    return request('POST','/api/simulation/telemetry',
                        json={'device_id':'thermometer_1','state':state},headers=headers)
                telemetry({'temperature':35,'humidity':50,'smoke':900,'rain':950})
                snap = request('GET','/api/dashboard/snapshot')
                devices = {d['device_id']:d for d in snap['devices']}
                assert devices['exhaust_fan']['state']['power'] is True
                assert devices['window_1']['state']['position']=='closed'
                codes = {a['code'] for a in request('GET','/api/alerts')['items'] if a['active']}
                assert {'temperature.high','smoke.detected','rain.detected'} <= codes
                checks['temperature_smoke_rain_linkage'] = True
                key = 'edge-verify-'+str(time.time_ns())
                command = {'action':'set','params':{'power':True,'brightness':80}}
                one = request('POST','/api/devices/main_light/commands',json=command,
                    headers={**headers,'Idempotency-Key':key})
                two = request('POST','/api/devices/main_light/commands',json=command,
                    headers={**headers,'Idempotency-Key':key})
                assert one['command_id']==two['command_id'] and one['status']=='acked'
                checks['mock_ack_and_idempotency'] = True
                telemetry({'temperature':26,'humidity':45,'smoke':0,'rain':0})
                snap = request('GET','/api/dashboard/snapshot')
                assert not next(d for d in snap['devices'] if d['device_id']=='exhaust_fan')['state']['power']
                checks['temperature_hysteresis_recovery'] = True
                history = request('GET','/api/sensors/history?metric=temperature')
                assert history[0]['points']
                checks['sql_sensor_history'] = True
                telemetry({'light':512})
                sparse = request('GET','/api/dashboard/snapshot')['sensors']
                readings = {s['metric']:s['value'] for s in sparse}
                assert readings['temperature']==26 and readings['humidity']==45 and readings['light']==512
                assert request('GET','/api/sensors/history?metric=light')[0]['points']
                checks['sparse_telemetry_preserves_other_metrics_and_light_history'] = True
                def door(position):
                    request('POST','/api/devices/front_door/commands',headers=headers,
                        json={'action':'set','params':{'position':position}})
                    return next(d for d in request('GET','/api/dashboard/snapshot')['devices'] if d['device_id']=='front_door')
                first = door('open')['open_since']
                assert first and door('open')['open_since']==first
                assert door('closed')['open_since'] is None
                assert door('open')['open_since']!=first
                door('closed')
                checks['mysql_door_open_since_transition_semantics'] = True
                alert = request('GET','/api/alerts')['items'][0]
                request('POST',f"/api/alerts/{alert['id']}/ack",headers=headers)
                checks['alert_ack'] = True
                # Verify the real face registration path without changing team identities.
                probe = 'probe_'+str(time.time_ns())
                with photos[0].open('rb') as stream:
                    result = request('POST','/api/person/add',headers=headers,
                        data={'name':probe,'user_id':probe},files={'face_image':('probe.jpg',stream,'image/jpeg')})
                assert result['user_id']==probe
                request('DELETE','/api/person/delete?user_id='+probe,headers=headers)
                assert all(p['user_id']!=probe for p in request('GET','/api/person/list'))
                checks['person_register_and_revoke'] = True
            finally:
                request('PUT','/api/settings',json=original,headers=headers)
                request('POST','/api/simulation/telemetry',headers=headers,json={
                    'device_id':'thermometer_1','state':{'temperature':26,'humidity':45,'smoke':0,'rain':0}})
                request('POST','/api/devices/main_light/commands',headers=headers,
                    json={'action':'set','params':{'power':False,'brightness':0}})
                request('POST','/api/devices/front_door/commands',headers=headers,
                    json={'action':'set','params':{'position':'closed'}})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--exercise',action='store_true')
    args = parser.parse_args()
    report = verify(args.root,args.exercise)
    target = args.root/'shared/verification.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print('Saved:',target)


if __name__=='__main__':
    main()
