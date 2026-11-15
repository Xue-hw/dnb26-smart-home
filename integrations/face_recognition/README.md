# 人脸识别交付

该目录保留本次确认上传的人脸识别完整交付内容：

- `register.py`：读取 `photos/` 中的图片并生成 `known_faces.pkl`；
- `recognize.py`：使用摄像头进行实时人脸识别；
- `liveness.py`：在人脸识别基础上使用 dlib 68 点关键点计算 EAR，检测眨眼活体；
- `shape_predictor_68_face_landmarks.dat`：dlib 关键点模型；
- `known_faces.pkl`：已注册人脸特征；
- `photos/`：本次交付包含的两张注册照片。

## 运行依赖

脚本依赖 `face_recognition`、`opencv-python`、`dlib`、`numpy` 和 `scipy`。当前脚本使用相对路径，运行目录应为本目录，或后续整合时改成配置化路径。

## 隐私与部署说明

本目录包含生物特征数据和个人照片，按用户本次确认保留。后续公开发布、共享给其他人员或部署到生产设备前，应重新评估是否需要移除这些文件，并把授权人员数据改为设备本地受控存储。当前脚本仍是独立演示程序，尚未接入仓库中的 FastAPI、数据库和 YOLO 服务。

已完成 Python 语法编译检查。`liveness.py` 当前把活体通过状态保存在进程级变量中，人员切换或离开画面后需要在整合阶段重置识别会话，避免继承上一位人员的通过结果。
