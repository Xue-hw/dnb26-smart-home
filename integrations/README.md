# 组员交付集成资料

本目录保存 DnB26 智能家居项目中由组员交付的 GUI、数据库、人脸识别和硬件资料。GUI、MySQL 与人脸模块已接入 FastAPI/YOLO 系统；硬件新增整合版和电脑网关，目前仅完成本地修改与验证，尚未部署或烧录。

## 子目录

- `gui/`：React + TypeScript + Vite + Capacitor GUI 源码与交付文档，不包含 `dist/` 和 APK 构建制品。
- `database/`：MySQL 建库脚本、`pymysql` 数据访问工具和自检脚本。
- `face_recognition/`：人脸注册、实时识别、眨眼活体检测脚本，以及本次交付中明确要求保留的人脸照片、人脸特征文件和 dlib 关键点模型。
- `hardware/`：硬件原始交付、整合 UNO 固件、RFID UID 白名单与电脑 USB 转发程序，见 [硬件入口](hardware/README.md)。

系统运行与部署状态见 [整合说明](../docs/system-integration.md)，本地硬件控制规则和后续联调见 [硬件整合说明](../docs/hardware-integration.md)。
