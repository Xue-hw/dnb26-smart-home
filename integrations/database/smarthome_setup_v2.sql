-- =============================================================
-- 智能家居 IoT 数据库一键建表脚本 v2（MySQL）
-- 对应 DnB26 题目要求：
--   1) 管理信息：存储和管理授权人员信息      -> authorized_users
--   2) 物体识别 + 人脸识别"2真1假"           -> security_vision_logs
--   3) GUI 展示 + 按时间区间检索历史数据      -> device_current_status / system_history_logs
--   4) 挑战项：GUI 远程控制灯/空调            -> 复用 device_current_status
-- 用法：mysql -u root -p < smarthome_setup_v2.sql
-- =============================================================

CREATE DATABASE IF NOT EXISTS smarthome_db DEFAULT CHARACTER SET utf8mb4;
USE smarthome_db;

-- 1. 设备当前状态表：只存每台设备的最新状态，供 GUI 实时渲染
CREATE TABLE IF NOT EXISTS device_current_status (
    device_id VARCHAR(50) PRIMARY KEY,
    device_type VARCHAR(30) NOT NULL,
    current_value VARCHAR(30) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 2. 环境与设备历史日志表：存全量时序数据，供"时间区间检索 + 统计分析"
CREATE TABLE IF NOT EXISTS system_history_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    data_type VARCHAR(30) NOT NULL,        -- temperature / light_brightness / door_state / window_state / fan
    device_id VARCHAR(50) NOT NULL,
    num_value FLOAT,                       -- 数值型：温度、亮度
    str_value VARCHAR(30),                 -- 状态型：open / closed / on / off
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_data_time (data_type, timestamp)   -- 联合索引，优化时间区间检索
);

-- 3. 白名单用户表（v2 新增）：对应"管理信息——存储和管理授权人员信息"
CREATE TABLE IF NOT EXISTS authorized_users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    face_feature_path VARCHAR(255),        -- 人脸特征文件路径，供算法比对
    pin_code VARCHAR(6) DEFAULT '123456',  -- 备用 PIN 码
    is_active TINYINT DEFAULT 1,           -- 1=启用 0=禁用
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 门禁与视觉识别安全日志表：记录"2真1假"全部测试事件，支持答辩溯源
CREATE TABLE IF NOT EXISTS security_vision_logs (
    event_id INT AUTO_INCREMENT PRIMARY KEY,
    snapshot_path VARCHAR(255) NOT NULL,
    yolo_objects VARCHAR(255),
    face_auth_result VARCHAR(50),          -- true_1_pass / true_2_pass / fake_fail / unknown
    action_taken VARCHAR(50),              -- gate_opened / access_denied
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 预置设备初始状态
INSERT IGNORE INTO device_current_status (device_id, device_type, current_value) VALUES
('front_door', 'door', 'closed'),
('window_1', 'window', 'closed'),
('main_light', 'light', '0'),
('exhaust_fan', 'fan', 'off'),
('thermometer_1', 'temperature', '0');

-- 预置一个授权用户示例（验收时可现场演示增删）
INSERT IGNORE INTO authorized_users (username, face_feature_path, pin_code) VALUES
('demo_user', 'static/faces/demo_user.pkl', '123456');
