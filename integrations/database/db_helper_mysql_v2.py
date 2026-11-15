# -*- coding: utf-8 -*-
"""
db_helper_mysql_v2.py
智能家居 IoT 数据库工具层 v2（MySQL 版）

对照 DnB26 题目（物联网+智科方向）四项要求封装接口：
  ① 管理信息   -> add_authorized_user / verify_pin / list_authorized_users / set_user_active
  ② 2真1假     -> log_security_event（写入）+ get_security_logs（溯源查询）
  ③ GUI 展示   -> get_all_device_status（实时）+ get_historical_data（时间区间检索）
  ④ 远程控制   -> update_device_and_log（硬件上报与 GUI 远程控制共用同一入口）
"""
import pymysql

# 数据库连接配置（改成你自己本地的 MySQL 密码）
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '密码',  # 填入你登录 mysql> 时用的密码
    'database': 'smarthome_db',
    'charset': 'utf8mb4'
}

# 数值型数据类型（走 num_value 字段），其余一律按状态型存 str_value
NUMERIC_TYPES = ('temperature', 'light_brightness')


def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


# =============================================================
# ③④ 硬件上报 / GUI 远程控制 / 实时状态查询
# =============================================================

def update_device_and_log(device_id, data_type, value):
    """
    更新设备最新状态表，并在历史日志表追加一条记录。
    硬件数据上报、GUI 远程开关灯/空调都调这一个函数。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql_status = """
            INSERT INTO device_current_status (device_id, device_type, current_value)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE current_value = VALUES(current_value)
        """
        cursor.execute(sql_status, (device_id, data_type, str(value)))

        if data_type in NUMERIC_TYPES:
            sql_log = "INSERT INTO system_history_logs (data_type, device_id, num_value) VALUES (%s, %s, %s)"
            cursor.execute(sql_log, (data_type, device_id, float(value)))
        else:
            sql_log = "INSERT INTO system_history_logs (data_type, device_id, str_value) VALUES (%s, %s, %s)"
            cursor.execute(sql_log, (data_type, device_id, str(value)))

        conn.commit()
        return True
    except Exception as e:
        print(f"❌ MySQL 写入失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_all_device_status():
    """
    【GUI 用】读取全部设备的最新状态，供前端实时渲染。
    :return: [{'device_id':..., 'device_type':..., 'current_value':..., 'updated_at':...}, ...]
    """
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT device_id, device_type, current_value, updated_at FROM device_current_status")
        rows = cursor.fetchall()
        for r in rows:
            r['updated_at'] = str(r['updated_at'])
        return rows
    except Exception as e:
        print(f"❌ 设备状态查询失败: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_historical_data(data_type, start_str, end_str):
    """
    【GUI 用】按时间区间检索历史数据（题目核心要求：特定时间间隔检索温度/灯/门窗状态）。
    :param data_type: temperature / light_brightness / door_state / window_state / fan
    :param start_str: 起始时间，格式 '2026-07-06 08:00:00'
    :param end_str:   结束时间，格式 '2026-07-06 12:00:00'
    :return: [{'value':..., 'timestamp':...}, ...] 按时间升序，可直接喂给前端折线图
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT num_value, str_value, timestamp
            FROM system_history_logs
            WHERE data_type = %s AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp ASC
        """, (data_type, start_str, end_str))
        rows = cursor.fetchall()
        return [{'value': r[0] if r[0] is not None else r[1], 'timestamp': str(r[2])} for r in rows]
    except Exception as e:
        print(f"❌ 历史数据查询失败: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# =============================================================
# ① 授权人员管理（v2 新增，对应"存储和管理授权人员信息"）
# =============================================================

def add_authorized_user(username, face_feature_path=None, pin_code='123456'):
    """新增授权人员（白名单）。返回 True/False。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO authorized_users (username, face_feature_path, pin_code) VALUES (%s, %s, %s)",
            (username, face_feature_path, pin_code))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ 新增用户失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def verify_pin(pin_code):
    """
    PIN 码开门验证。命中且账号启用则返回用户名，否则返回 None。
    人脸识别算法也可先查本表拿 face_feature_path 做比对。
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT username FROM authorized_users WHERE pin_code = %s AND is_active = 1 LIMIT 1",
            (pin_code,))
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        print(f"❌ PIN 验证失败: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def list_authorized_users():
    """【GUI 用】列出全部授权人员（管理界面展示/增删入口）。"""
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute(
            "SELECT user_id, username, face_feature_path, is_active, created_at FROM authorized_users ORDER BY user_id")
        rows = cursor.fetchall()
        for r in rows:
            r['created_at'] = str(r['created_at'])
        return rows
    except Exception as e:
        print(f"❌ 用户列表查询失败: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def set_user_active(username, is_active):
    """启用/禁用某个授权人员（is_active: 1 或 0）。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE authorized_users SET is_active = %s WHERE username = %s",
                       (is_active, username))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ 用户状态更新失败: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


# =============================================================
# ② 安防视觉日志（YOLO + 人脸识别"2真1假"）
# =============================================================

def log_security_event(snapshot_path, yolo_objects, face_res, action):
    """
    记录 YOLO 和人脸识别安全日志。
    face_res 约定: true_1_pass / true_2_pass / fake_fail / unknown
    action   约定: gate_opened / access_denied
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO security_vision_logs (snapshot_path, yolo_objects, face_auth_result, action_taken)
            VALUES (%s, %s, %s, %s)
        """, (snapshot_path, yolo_objects, face_res, action))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ 安全日志写入失败: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def get_security_logs(limit=20):
    """
    【GUI/答辩用】查询最近的安全识别事件，支撑"2真1假"演示溯源。
    :return: 按时间倒序的事件列表
    """
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("""
            SELECT event_id, snapshot_path, yolo_objects, face_auth_result, action_taken, timestamp
            FROM security_vision_logs ORDER BY timestamp DESC LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        for r in rows:
            r['timestamp'] = str(r['timestamp'])
        return rows
    except Exception as e:
        print(f"❌ 安全日志查询失败: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
