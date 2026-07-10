# DnB26 无人机/灭火器联合识别模型包

模型文件：weights/dnb26_drone_fire_yolo11n_best.pt

类别：
0: drone
1: fire_extinguisher

推荐推理参数：
conf=0.35
imgsz=960

当前主模型来源：runs/detect/dnb26_drone_fire_yolo11n_continue_2/weights/best.pt

验证集总体指标：
precision=0.862
recall=0.780
mAP50=0.842
mAP50-95=0.488

按类别指标：
drone: P=0.862, R=0.725, mAP50=0.808, mAP50-95=0.391
fire_extinguisher: P=0.862, R=0.836, mAP50=0.875, mAP50-95=0.586

说明：
- 后续实际展示建议使用项目摄像头现场照片继续微调。
- 本包不包含训练数据集、摄像头截图、完整 runs 目录或虚拟环境。
