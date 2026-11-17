"""MySQL persistence. No in-memory fallback is used by the running system."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def json_default(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()
    raise TypeError(f'Cannot encode {type(value).__name__}')


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=json_default)


def public_command(command):
    """Remove private retry metadata and credentials from command read models."""
    result = {key: value for key, value in command.items() if key != '_sensitive_fingerprint'}
    if isinstance(result.get('params'), dict) and 'pin' in result['params']:
        result['params'] = {**result['params'], 'pin': '[redacted]'}
    return result


def parse_time(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


class RepositoryUnavailable(RuntimeError):
    pass


SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS dnb_devices (
        device_id VARCHAR(50) PRIMARY KEY, name VARCHAR(100) NOT NULL,
        kind VARCHAR(30) NOT NULL, state_json LONGTEXT NOT NULL, source VARCHAR(20) NOT NULL,
        updated_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3), open_since DATETIME(3) NULL)''',
    '''CREATE TABLE IF NOT EXISTS dnb_person_meta (
        person_id INT PRIMARY KEY, public_id VARCHAR(64) UNIQUE NOT NULL,
        avatar_url VARCHAR(255), feature_version VARCHAR(30) DEFAULT 'v1')''',
    '''CREATE TABLE IF NOT EXISTS dnb_commands (
        command_id VARCHAR(64) PRIMARY KEY, idempotency_key VARCHAR(128) UNIQUE,
        device_id VARCHAR(50) NOT NULL, payload_json LONGTEXT NOT NULL,
        status VARCHAR(20) NOT NULL, requested_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
        acked_at TIMESTAMP(3) NULL, error_message VARCHAR(500), source VARCHAR(30) NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS dnb_events (
        event_id VARCHAR(64) PRIMARY KEY, category VARCHAR(30) NOT NULL,
        device_id VARCHAR(50), payload_json LONGTEXT NOT NULL,
        occurred_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
        INDEX idx_dnb_events_time(category, occurred_at))''',
    '''CREATE TABLE IF NOT EXISTS dnb_alerts (
        id VARCHAR(64) PRIMARY KEY, code VARCHAR(100) NOT NULL,
        severity VARCHAR(20) NOT NULL, message VARCHAR(500) NOT NULL,
        active TINYINT NOT NULL DEFAULT 1, acknowledged TINYINT NOT NULL DEFAULT 0,
        created_at TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3), resolved_at TIMESTAMP(3) NULL,
        INDEX idx_dnb_alert_code(code, active))''',
    '''CREATE TABLE IF NOT EXISTS dnb_settings (
        settings_id INT PRIMARY KEY, payload_json LONGTEXT NOT NULL)''',
]


class Repository:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def connection(self):
        import pymysql
        conn = None
        try:
            conn = pymysql.connect(host=self.settings.database_host, port=self.settings.database_port,
                user=self.settings.database_user, password=self.settings.database_password,
                database=self.settings.database_name, charset='utf8mb4', connect_timeout=3,
                read_timeout=8, write_timeout=8, cursorclass=pymysql.cursors.DictCursor,
                init_command="SET time_zone = '+00:00'")
            yield conn
            conn.commit()
        except pymysql.MySQLError as exc:
            if conn:
                conn.rollback()
            # Avoid leaking host credentials or raw database messages to API responses.
            raise RepositoryUnavailable(f'MySQL 操作失败（错误码 {exc.args[0] if exc.args else "unknown"}）') from exc
        finally:
            if conn:
                conn.close()

    def initialize(self):
        source = Path(__file__).resolve().parents[1] / 'integrations/database/smarthome_setup_v2.sql'
        text = re.sub(r'--[^\n]*', '', source.read_text(encoding='utf-8'))
        with self.connection() as conn, conn.cursor() as cursor:
            for statement in text.split(';'):
                statement = statement.strip()
                # The database itself is provisioned by deployment, using least-privilege credentials.
                if statement and not statement.upper().startswith(('CREATE DATABASE', 'USE ')):
                    cursor.execute(statement)
            for statement in SCHEMA:
                cursor.execute(statement)
            cursor.execute("SHOW COLUMNS FROM dnb_devices LIKE 'open_since'")
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE dnb_devices ADD COLUMN open_since DATETIME(3) NULL')
                cursor.execute("UPDATE dnb_devices SET open_since=updated_at WHERE kind='door' AND JSON_UNQUOTE(JSON_EXTRACT(state_json,'$.position'))='open'")
            # Keep the delivered SQL unchanged, but its exact unregistered demo row
            # is not a usable authorization. A real registration has metadata or a
            # different feature path and must remain untouched.
            cursor.execute('''UPDATE authorized_users u SET u.is_active=0
                WHERE u.username='demo_user' AND u.face_feature_path='static/faces/demo_user.pkl'
                AND u.pin_code='123456' AND u.is_active=1
                AND NOT EXISTS(SELECT 1 FROM dnb_person_meta m WHERE m.person_id=u.user_id)''')

    def ping(self):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()

    def get_settings(self):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT payload_json FROM dnb_settings WHERE settings_id=1')
            row = cursor.fetchone()
            return json.loads(row['payload_json']) if row else {}

    def save_settings(self, values):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('INSERT INTO dnb_settings(settings_id,payload_json) VALUES(1,%s) '
                'ON DUPLICATE KEY UPDATE payload_json=VALUES(payload_json)', (encode(values),))

    def list_people(self, include_features=False, include_inactive=False):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('''SELECT u.user_id AS internal_id, COALESCE(m.public_id,CAST(u.user_id AS CHAR)) AS user_id,
                u.username AS name,u.face_feature_path,u.created_at,m.avatar_url,
                COALESCE(m.feature_version,'legacy') AS feature_version
                FROM authorized_users u LEFT JOIN dnb_person_meta m ON m.person_id=u.user_id
                ''' + ('' if include_inactive else 'WHERE u.is_active=1 ') + 'ORDER BY u.user_id')
            rows = cursor.fetchall()
        for row in rows:
            row['created_at'] = json_default(row['created_at'])
            if not include_features:
                row.pop('face_feature_path', None)
                row.pop('internal_id', None)
        return rows

    def add_person(self, public_id, name, feature_path, avatar):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT m.person_id,u.is_active FROM dnb_person_meta m JOIN authorized_users u ON u.user_id=m.person_id WHERE m.public_id=%s', (public_id,))
            existing = cursor.fetchone()
            if existing and existing['is_active']:
                raise ValueError('人员编号已存在')
            cursor.execute('SELECT user_id,is_active FROM authorized_users WHERE username=%s', (name,))
            named = cursor.fetchone()
            if named and named['is_active'] and (not existing or named['user_id']!=existing['person_id']):
                raise ValueError('姓名已存在，请使用可区分的姓名')
            if existing:
                cursor.execute('UPDATE authorized_users SET username=%s,face_feature_path=%s,is_active=1 WHERE user_id=%s',
                               (name,str(feature_path),existing['person_id']))
                cursor.execute('UPDATE dnb_person_meta SET avatar_url=%s,feature_version=%s WHERE person_id=%s',
                               (avatar,uuid.uuid4().hex[:20],existing['person_id']))
            elif named:
                cursor.execute('UPDATE authorized_users SET face_feature_path=%s,is_active=1 WHERE user_id=%s',
                               (str(feature_path),named['user_id']))
                cursor.execute('INSERT INTO dnb_person_meta(person_id,public_id,avatar_url) VALUES(%s,%s,%s) '
                    'ON DUPLICATE KEY UPDATE public_id=VALUES(public_id),avatar_url=VALUES(avatar_url)',
                               (named['user_id'],public_id,avatar))
            else:
                cursor.execute('INSERT INTO authorized_users(username,face_feature_path,pin_code,is_active) VALUES(%s,%s,NULL,1)',
                               (name, str(feature_path)))
                cursor.execute('INSERT INTO dnb_person_meta(person_id,public_id,avatar_url) VALUES(%s,%s,%s)',
                               (cursor.lastrowid, public_id, avatar))
        return next(p for p in self.list_people() if p['user_id'] == public_id)

    def delete_person(self, public_id):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('''UPDATE authorized_users u LEFT JOIN dnb_person_meta m ON m.person_id=u.user_id
                SET u.is_active=0 WHERE COALESCE(m.public_id,CAST(u.user_id AS CHAR))=%s AND u.is_active=1''', (public_id,))
            if not cursor.rowcount:
                raise KeyError('人员不存在或已经停用')

    def is_authorized(self, public_id):
        return any(p['user_id'] == public_id for p in self.list_people())

    def update_device(self, device_id, name, kind, state, source):
        with self.connection() as conn, conn.cursor() as cursor:
            # Hardware may report one changed metric at a time. Preserve other
            # current values, while history below records only this new sample.
            cursor.execute('SELECT state_json FROM dnb_devices WHERE device_id=%s FOR UPDATE',(device_id,))
            existing = cursor.fetchone()
            merged = {**(json.loads(existing['state_json']) if existing else {}),**state}
            cursor.execute('''INSERT INTO dnb_devices(device_id,name,kind,state_json,source,updated_at,open_since)
                VALUES(%s,%s,%s,%s,%s,CURRENT_TIMESTAMP(3),IF(%s,CURRENT_TIMESTAMP(3),NULL)) ON DUPLICATE KEY UPDATE
                open_since=IF(VALUES(kind)='door' AND JSON_UNQUOTE(JSON_EXTRACT(VALUES(state_json),'$.position'))='open',
                    IF(kind='door' AND JSON_UNQUOTE(JSON_EXTRACT(state_json,'$.position'))='open',
                        COALESCE(open_since,updated_at),CURRENT_TIMESTAMP(3)),NULL),
                name=VALUES(name),kind=VALUES(kind),state_json=VALUES(state_json),source=VALUES(source),updated_at=CURRENT_TIMESTAMP(3)''',
                (device_id, name, kind, encode(merged), source, kind=='door' and merged.get('position')=='open'))
            for metric, value in state.items():
                numeric = type(value) in (int, float)
                cursor.execute('INSERT INTO system_history_logs(data_type,device_id,num_value,str_value) VALUES(%s,%s,%s,%s)',
                    (kind + '.' + metric, device_id, value if numeric else None, str(value)[:30] if not numeric else None))
            # Mirror a compact scalar into the original team table, never exceed VARCHAR(30).
            scalar = next(iter(merged.values()), 'unknown')
            cursor.execute('''INSERT INTO device_current_status(device_id,device_type,current_value) VALUES(%s,%s,%s)
                ON DUPLICATE KEY UPDATE current_value=VALUES(current_value)''', (device_id, kind, str(scalar)[:30]))

    def devices(self):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dnb_devices ORDER BY device_id')
            rows = cursor.fetchall()
            cursor.execute("SELECT device_id,data_type,MAX(timestamp) AS measured_at FROM system_history_logs "
                           "WHERE data_type LIKE 'sensor.%' GROUP BY device_id,data_type")
            samples = {(s['device_id'],s['data_type'].removeprefix('sensor.')):json_default(s['measured_at'])
                       for s in cursor.fetchall()}
        for row in rows:
            row['state'] = json.loads(row.pop('state_json'))
            row['updated_at'] = json_default(row['updated_at'])
            row['open_since'] = json_default(row['open_since']) if row.get('open_since') else None
            if row['kind']=='sensor':
                row['metric_measured_at'] = {metric:samples.get((row['device_id'],metric)) for metric in row['state']}
        return rows

    def sensor_history(self, metric, start, end, device_id=None):
        clauses, args = ['data_type=%s'], ['sensor.' + metric]
        if start:
            clauses.append('timestamp >= %s'); args.append(parse_time(start))
        if end:
            clauses.append('timestamp <= %s'); args.append(parse_time(end))
        if device_id:
            clauses.append('device_id=%s'); args.append(device_id)
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT num_value,timestamp FROM system_history_logs WHERE ' + ' AND '.join(clauses) + ' ORDER BY timestamp LIMIT 10000', args)
            rows = cursor.fetchall()
        return {'metric': metric, 'unit': '°C' if metric == 'temperature' else '%' if metric == 'humidity' else 'raw',
            'points': [{'ts':json_default(r['timestamp']), 'value':r['num_value']} for r in rows], 'aggregated':False}

    def event(self, category, payload, device_id=None):
        event_id = payload.get('event_id') or uuid.uuid4().hex
        payload = {**payload, 'event_id':event_id, 'occurred_at':payload.get('occurred_at', utcnow())}
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('INSERT INTO dnb_events(event_id,category,device_id,payload_json) VALUES(%s,%s,%s,%s)',
                           (event_id,category,device_id,encode(payload)))
            if category == 'recognition':
                cursor.execute('INSERT INTO security_vision_logs(snapshot_path,yolo_objects,face_auth_result,action_taken) VALUES(%s,%s,%s,%s)',
                    ((payload.get('image_url') or '')[:255], ','.join(d['label'] for d in payload.get('detections', []))[:255],
                     str(payload.get('liveness_status', 'unknown'))[:50],
                     ('gate_requested' if payload.get('access_granted') else 'access_denied') if payload.get('type')=='face' else 'observed'))
        return payload

    def events(self, category, start=None, end=None, device_id=None, page=1, page_size=20):
        clauses, args = ['category=%s'], [category]
        if start:
            clauses.append('occurred_at>=%s'); args.append(parse_time(start))
        if end:
            clauses.append('occurred_at<=%s'); args.append(parse_time(end))
        if device_id:
            clauses.append('device_id=%s'); args.append(device_id)
        where = ' AND '.join(clauses)
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) AS n FROM dnb_events WHERE '+where, args)
            count = cursor.fetchone()['n']
            cursor.execute('SELECT payload_json FROM dnb_events WHERE '+where+' ORDER BY occurred_at DESC LIMIT %s OFFSET %s',
                           [*args, page_size, (page-1)*page_size])
            rows = cursor.fetchall()
        return {'items':[json.loads(r['payload_json']) for r in rows], 'total':count, 'page':page, 'page_size':page_size}

    def command(self, command_id):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dnb_commands WHERE command_id=%s', (command_id,))
            row = cursor.fetchone()
        if not row:
            raise KeyError('命令不存在')
        return self._command(row)

    @staticmethod
    def _command(row):
        return public_command({**json.loads(row['payload_json']), 'command_id':row['command_id'], 'status':row['status'],
            'requested_at':json_default(row['requested_at']),
            'acked_at':json_default(row['acked_at']) if row['acked_at'] else None,
            'error_message':row['error_message'], 'source':row['source']})

    def create_command(self, device_id, payload, source, key=None):
        with self.connection() as conn, conn.cursor() as cursor:
            if key:
                cursor.execute('SELECT * FROM dnb_commands WHERE idempotency_key=%s FOR UPDATE', (key,))
                row = cursor.fetchone()
                if row:
                    if row['device_id'] != device_id or json.loads(row['payload_json']) != payload:
                        raise ValueError('幂等键已用于其他命令')
                    return self._command(row), False
            command_id = uuid.uuid4().hex
            cursor.execute('INSERT INTO dnb_commands(command_id,idempotency_key,device_id,payload_json,status,source) VALUES(%s,%s,%s,%s,%s,%s)',
                           (command_id,key,device_id,encode(payload),'pending',source))
        return self.command(command_id), True

    def finish_command(self, command_id, status, error=None):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('UPDATE dnb_commands SET status=%s,error_message=%s,acked_at=IF(%s=\'acked\',CURRENT_TIMESTAMP(3),NULL) WHERE command_id=%s AND status=\'pending\'',
                           (status,error,status,command_id))
        return self.command(command_id)

    def expire_commands(self, seconds=30):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute("UPDATE dnb_commands SET status='timeout',error_message='设备确认超时，结果未知' WHERE status='pending' AND requested_at<TIMESTAMPADD(SECOND,-%s,CURRENT_TIMESTAMP)", (seconds,))

    def alert(self, code, message, severity='warning', active=True):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT id FROM dnb_alerts WHERE code=%s AND active=1 LIMIT 1', (code,))
            row = cursor.fetchone()
            if active and not row:
                cursor.execute('INSERT INTO dnb_alerts(id,code,severity,message) VALUES(%s,%s,%s,%s)',
                               (uuid.uuid4().hex,code,severity,message[:500]))
            elif not active and row:
                cursor.execute('UPDATE dnb_alerts SET active=0,resolved_at=CURRENT_TIMESTAMP(3) WHERE code=%s AND active=1', (code,))

    def alerts(self):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dnb_alerts ORDER BY active DESC,created_at DESC LIMIT 100')
            rows = cursor.fetchall()
        for row in rows:
            row['active'], row['acknowledged'] = bool(row['active']), bool(row['acknowledged'])
            row['created_at'] = json_default(row['created_at'])
            row['resolved_at'] = json_default(row['resolved_at']) if row['resolved_at'] else None
        return {'items': rows}

    def ack_alert(self, alert_id):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute('UPDATE dnb_alerts SET acknowledged=1 WHERE id=%s', (alert_id,))
            if not cursor.rowcount:
                cursor.execute('SELECT id FROM dnb_alerts WHERE id=%s', (alert_id,))
                if not cursor.fetchone():
                    raise KeyError('报警不存在')

    def prune_recognition(self, cutoff):
        with self.connection() as conn, conn.cursor() as cursor:
            cursor.execute("DELETE FROM dnb_events WHERE category='recognition' AND occurred_at<%s", (cutoff,))
            cursor.execute('DELETE FROM security_vision_logs WHERE timestamp<%s', (cutoff,))
