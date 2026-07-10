# YOLO 目标识别模型训练与香橙派部署验收汇报

## 1. 汇报开场

老师好，我这部分小学期项目主要完成的是基于 YOLO 的目标识别模型训练、推理脚本开发，以及在香橙派上的部署验证。目前模型已经可以在电脑端和香橙派端正常运行，能够通过摄像头或图片输入完成目标识别。

本项目最终围绕两个自定义目标类别进行识别：

| 类别编号 | 类别名称 | 含义 |
| --- | --- | --- |
| 0 | `drone` | 无人机 |
| 1 | `fire_extinguisher` | 灭火器 |

我选择 YOLO11n 作为主模型，是因为它模型体积较小、推理速度较快，适合后续部署到香橙派这类边缘计算设备上；同时它兼容 Ultralytics 的统一接口，方便训练、验证、导出和部署。

## 2. 我的主要工作内容

### 2.1 数据集整理与配置

我首先整理了无人机和灭火器两类目标的数据集，并按照 YOLO 格式组织为 `images/train`、`images/val`、`labels/train`、`labels/val` 四个目录。

当前使用的数据集配置文件为：

```text
D:\Codework\dnb26-smart-home\data\datasets\drone_fire_extinguisher\data.yaml
```

数据集规模如下：

| 数据划分 | 图片数量 | 标注数量 |
| --- | ---: | ---: |
| 训练集 | 3762 | 3762 |
| 验证集 | 691 | 691 |

`data.yaml` 中定义了两个类别：

```yaml
names:
  0: drone
  1: fire_extinguisher
```

验收时可以这样讲：

> 我没有只使用通用预训练模型，而是把项目需要识别的无人机和灭火器整理成 YOLO 格式数据集，并配置了训练集、验证集和类别映射，使模型能够学习项目自己的目标类别。

### 2.2 模型选择与训练

项目采用 YOLO11n 作为基础模型进行微调。训练脚本为：

```text
D:\Codework\dnb26-smart-home\scripts\train_drone_fire_yolo.py
```

训练命令示例：

```powershell
cd D:\Codework\dnb26-smart-home
.\.venv\Scripts\activate
python scripts\train_drone_fire_yolo.py --data data\datasets\drone_fire_extinguisher\data.yaml --model models\yolo11n.pt --epochs 50 --imgsz 640 --batch 16 --device 0 --name dnb26_drone_fire_yolo11n
```

后续我又进行了继续训练和参数调整，最终主模型来源为：

```text
D:\Codework\dnb26-smart-home\runs\detect\dnb26_drone_fire_yolo11n_continue_2\weights\best.pt
```

为了部署方便，我将最终权重整理到：

```text
D:\Codework\dnb26-smart-home\deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt
```

### 2.3 模型验证结果

最终模型在验证集上的总体指标如下：

| 指标 | 数值 |
| --- | ---: |
| Precision | 0.862 |
| Recall | 0.780 |
| mAP50 | 0.842 |
| mAP50-95 | 0.488 |

按类别统计：

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| drone | 0.862 | 0.725 | 0.808 | 0.391 |
| fire_extinguisher | 0.862 | 0.836 | 0.875 | 0.586 |

验收时可以这样讲：

> 从结果看，模型对两个类别都已经具备可用的识别能力。其中灭火器类别的 mAP50 达到 0.875，无人机类别的 mAP50 达到 0.808。考虑到后续是边缘端实时识别场景，我选择了轻量化模型，在准确率和部署效率之间做了折中。

## 3. 推理与部署工作

### 3.1 电脑端图片识别命令

在 Windows 电脑上进入项目目录：

```powershell
cd D:\Codework\dnb26-smart-home
.\.venv\Scripts\activate
```

对单张图片进行识别：

```powershell
python scripts\detect_image.py data\datasets\drone_fire_extinguisher\images\train\drone_train_000000.jpg --model deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --output data\detections\drone_train_000000_detected.jpg
```

说明：

- `--model` 指定训练后的模型权重；
- `--conf 0.35` 是部署包中推荐的置信度阈值；
- `--imgsz 960` 是推荐推理分辨率；
- `--classes drone,fire_extinguisher` 表示只保留本项目需要识别的类别；
- `--output` 指定保存带检测框的输出图片。

### 3.2 电脑端视频实时识别命令

视频实时识别有两种输入方式：第一种是调用摄像头实时画面，第二种是读取本地视频文件逐帧识别。

电脑端调用默认摄像头进行实时识别：

```powershell
cd D:\Codework\dnb26-smart-home
.\.venv\Scripts\activate
python scripts\detect_camera.py --camera 0 --model deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480
```

电脑端调用本地视频文件进行逐帧识别：

```powershell
cd D:\Codework\dnb26-smart-home
.\.venv\Scripts\activate
python scripts\detect_camera.py --camera data\videos\demo.mp4 --model deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480
```

其中 `data\videos\demo.mp4` 需要替换为实际视频文件路径。

如果只想在终端输出识别结果、不弹出显示窗口，可以加上 `--no-window`：

```powershell
python scripts\detect_camera.py --camera 0 --model deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480 --no-window
```

### 3.3 香橙派端环境准备命令

香橙派使用 Linux 终端进入项目目录，例如：

```bash
cd ~/dnb26-smart-home
```

创建并激活 Python 虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安装依赖：

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

如果香橙派上使用的是无桌面环境，建议安装 headless 版本 OpenCV；如果需要弹出摄像头窗口，则需要普通 OpenCV 和图形界面支持。

### 3.4 香橙派端图片识别命令

香橙派端检测单张图片：

```bash
cd ~/dnb26-smart-home
source .venv/bin/activate
python scripts/detect_image.py data/datasets/drone_fire_extinguisher/images/train/drone_train_000000.jpg --model deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --output data/detections/drone_train_000000_detected.jpg
```

### 3.5 香橙派端视频实时识别命令

香橙派端调用摄像头实时识别：

```bash
cd ~/dnb26-smart-home
source .venv/bin/activate
python scripts/detect_camera.py --camera 0 --model deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480
```

香橙派端调用本地视频文件逐帧识别：

```bash
cd ~/dnb26-smart-home
source .venv/bin/activate
python scripts/detect_camera.py --camera data/videos/demo.mp4 --model deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480
```

其中 `data/videos/demo.mp4` 需要替换为实际视频文件路径。

如果香橙派没有接显示器，使用终端模式运行：

```bash
cd ~/dnb26-smart-home
source .venv/bin/activate
python scripts/detect_camera.py --camera 0 --model deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480 --no-window
```

### 3.6 ONNX 导出

为了便于后续在边缘设备上继续做推理加速，我还导出了 ONNX 模型：

```text
D:\Codework\dnb26-smart-home\deploy_export\weights\dnb26_drone_fire_yolo11n_best.onnx
```

导出命令示例：

```powershell
cd D:\Codework\dnb26-smart-home
.\.venv\Scripts\activate
python scripts\export_yolo11n_onnx.py --model deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt --imgsz 960 --opset 12
```

验收时可以这样讲：

> 当前香橙派上已经可以直接加载 `.pt` 模型完成识别。同时我也准备了 `.onnx` 格式，后续如果需要进一步提高推理速度，可以继续接入 ONNX Runtime 或香橙派对应的 NPU 推理工具链。

## 4. 项目中涉及的关键文件

| 文件或目录 | 作用 |
| --- | --- |
| `data/datasets/drone_fire_extinguisher/data.yaml` | YOLO 数据集配置 |
| `scripts/train_drone_fire_yolo.py` | 模型训练脚本 |
| `scripts/detect_image.py` | 图片识别脚本 |
| `scripts/detect_camera.py` | 摄像头或视频文件实时识别脚本 |
| `backend/vision/yolo_detector.py` | YOLO 推理封装类 |
| `deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt` | 最终部署用 PyTorch 权重 |
| `deploy_export/weights/dnb26_drone_fire_yolo11n_best.onnx` | 后续加速用 ONNX 权重 |
| `deploy_export/README.md` | 模型包说明和推荐推理参数 |
| `share/dnb26_drone_fire_model_package.zip` | 可拷贝到设备端的模型包 |

## 5. 验收现场推荐演示流程

### 第一步：说明模型目标

> 我负责的是视觉识别部分，目标是训练一个可以识别无人机和灭火器的轻量化 YOLO 模型，并部署到香橙派上运行。

### 第二步：展示数据和训练

> 我整理了 YOLO 格式数据集，包含 3762 张训练图片和 691 张验证图片。模型采用 YOLO11n 作为基础权重进行微调，训练完成后得到 `best.pt`，并根据验证集指标选择最终模型。

### 第三步：展示识别命令

电脑端：

```powershell
python scripts\detect_camera.py --camera 0 --model deploy_export\weights\dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480
```

香橙派端：

```bash
python scripts/detect_camera.py --camera 0 --model deploy_export/weights/dnb26_drone_fire_yolo11n_best.pt --conf 0.35 --imgsz 960 --classes drone,fire_extinguisher --width 640 --height 480
```

### 第四步：现场运行

> 现在我运行摄像头识别脚本，程序会实时读取摄像头画面，并对画面中的无人机或灭火器输出类别、置信度和检测框。如果没有图形界面，也可以使用 `--no-window` 在终端查看检测结果。

### 第五步：总结部署结果

> 目前模型已经完成从训练到部署的闭环：数据集整理、YOLO11n 微调、验证指标统计、模型导出、电脑端测试、香橙派端部署运行都已经完成。后续如果继续优化，可以增加真实场景图片继续微调，或者使用 ONNX/NPU 推理进一步提高香橙派端速度。

## 6. 老师可能会问的问题

### 问：为什么选择 YOLO11n？

答：YOLO11n 是轻量化模型，参数量和模型文件较小，适合边缘设备部署；同时它支持 Ultralytics API，训练、验证、导出和调用都比较统一。对于香橙派这类算力有限的设备，YOLO11n 比较适合作为实时识别的起点。

### 问：为什么置信度使用 0.35？

答：因为部署场景中目标可能受光照、角度、距离影响，阈值过高会漏检。当前模型包推荐 `conf=0.35`，是在检测召回和误检控制之间做的折中。实际展示时如果误检偏多，可以临时提高到 `0.5`。

### 问：模型是否只在电脑上能跑？

答：不是。电脑端主要用于训练和调试，最终模型包已经部署到香橙派，并且可以在香橙派上通过摄像头运行识别脚本。命令和电脑端基本一致，只是路径格式从 Windows 的反斜杠改为 Linux 的斜杠。

### 问：后续还能怎么优化？

答：可以从三个方向继续优化：第一，增加香橙派摄像头实际采集的图片继续微调，提高真实场景适应性；第二，导出 ONNX 后接入边缘端推理加速；第三，根据实际误检情况增加负样本，提高模型在复杂背景下的稳定性。

## 7. 一句话总结

本次工作完成了 YOLO 目标识别模型从数据集准备、模型训练、指标验证、模型导出到香橙派部署运行的完整流程，最终模型能够在电脑端和香橙派端对无人机、灭火器目标进行实时识别，满足小学期项目验收展示要求。
