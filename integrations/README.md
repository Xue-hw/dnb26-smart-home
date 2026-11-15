# 组员交付集成资料

本目录保存 DnB26 智能家居项目中由组员交付的 GUI、数据库和人脸识别资料。当前内容按“先归档、后整合”的方式保留，尚未把这些模块接入现有 FastAPI/YOLO 运行链路。

## 子目录

- `gui/`：React + TypeScript + Vite + Capacitor GUI 源码与交付文档，不包含 `dist/` 和 APK 构建制品。
- `database/`：MySQL 建库脚本、`pymysql` 数据访问工具和自检脚本。
- `face_recognition/`：人脸注册、实时识别、眨眼活体检测脚本，以及本次交付中明确要求保留的人脸照片、人脸特征文件和 dlib 关键点模型。

后续部署到 Orange Pi AIpro 20T 时，需要继续完成 API 契约对接、数据库方案选择、摄像头输入统一、模型推理资源适配和权限/隐私数据管理。
