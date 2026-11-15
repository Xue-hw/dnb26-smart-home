# -*- coding: utf-8 -*-
"""
run_test_v2.py — v2 全流程自检脚本
覆盖老师四项基本要求：授权人员管理 / 2真1假日志 / 实时状态 + 时间区间检索 / 远程控制写入
运行：python run_test_v2.py
"""
import time
from datetime import datetime, timedelta
from db_helper_mysql_v2 import (
    update_device_and_log, get_all_device_status, get_historical_data,
    add_authorized_user, verify_pin, list_authorized_users,
    log_security_event, get_security_logs,
)

passed = 0
total = 6

def check(ok, label):
    global passed
    if ok:
        passed += 1
        print(f"✅ 成功：{label}")
    else:
        print(f"❌ 失败：{label}（检查数据库密码 / 服务是否开启 / 是否已执行 smarthome_setup_v2.sql）")

print("======== 🚀 v2 全流程自检开始 ========")

# 1. 硬件上报：室内温度 28.5 ℃
check(update_device_and_log('thermometer_1', 'temperature', 28.5), "硬件上报温度 28.5℃")
time.sleep(1)

# 2. 远程控制模拟：GUI 远程打开风扇（温度联动）
check(update_device_and_log('exhaust_fan', 'fan', 'on'), "远程控制风扇 -> on")
time.sleep(1)

# 3. 授权人员管理：新增用户 + PIN 验证开门
uname = 'test_user_' + datetime.now().strftime('%H%M%S')
ok_add = add_authorized_user(uname, face_feature_path=f'static/faces/{uname}.pkl', pin_code='888888')
check(ok_add and verify_pin('888888') == uname, f"新增授权用户 {uname} 并通过 PIN 验证")
check(verify_pin('000000') is None, "错误 PIN 被正确拒绝")

# 4. 时间区间检索：查最近 10 分钟温度历史（GUI 折线图数据源）
now = datetime.now()
rows = get_historical_data('temperature', str(now - timedelta(minutes=10)), str(now))
check(len(rows) > 0, f"时间区间检索到 {len(rows)} 条温度历史数据")

# 5. 2真1假安防日志：照片伪造人脸被拦截
check(log_security_event('static/captures/fake_face_01.jpg', 'person', 'fake_fail', 'access_denied'),
      "2真1假拦截事件已写入安全日志")

# 6. 答辩溯源：读回安防日志 + 实时状态
logs = get_security_logs(5)
status = get_all_device_status()
check(len(logs) > 0 and len(status) > 0, f"答辩溯源查询正常（安防日志 {len(logs)} 条 / 设备状态 {len(status)} 台）")

print(f"\n======== 自检完毕：{passed}/{total} 项通过 ========")
if passed == total:
    print("✨ 全部通过，老师要求的四项核心功能均已覆盖！")
