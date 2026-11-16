# 灯泡三类模型训练记录

本次扩展保留原无人机、灭火器模型与数据，新增 `light_bulb` 类别，训练独立的三类候选模型。模型是否进入实际设备控制流程，仍应结合板端性能和摄像头实景测试决定。

## 类别与数据

| 类别编号 | 模型标签 | 中文名称 |
| --- | --- | --- |
| 0 | `drone` | 无人机 |
| 1 | `fire_extinguisher` | 灭火器 |
| 2 | `light_bulb` | 灯泡 |

旧数据来自项目已有 `data/datasets/drone_fire_extinguisher`。新灯泡数据来自 Google Open Images 官方人工边界框标注，类别 MID 为 `/m/0h8l4fh`，图像由 CVDF 的公开 S3 镜像逐张获取。未使用全图框、模型伪标签或合成图片替代人工检测标注。

- 标注文件：<https://storage.googleapis.com/openimages/2018_04/train/train-annotations-bbox.csv>
- 图像镜像说明：<https://github.com/cvdfoundation/open-images-dataset>
- 原项目许可说明：<https://github.com/openimages/dataset/blob/main/READMEV3.md>
- Open Images 标注许可为 CC BY 4.0；官方将图片列为 CC BY 2.0，同时要求使用者核实原图权利。此次图片保留在本地忽略目录，未随源码发布。

为控制下载量，脚本抽取上述标注文件固定前 768 MiB 内的灯泡记录，排除 `IsGroupOf=1` 和 `IsDepiction=1`。这是一份可复现的有限抽样，不代表整个 Open Images 灯泡类别。

| 来源 | 训练图片 | 验证图片 | 留出测试图片 |
| --- | ---: | ---: | ---: |
| 原无人机／灭火器数据，去除完全重复后 | 3748 | 690 | 0 |
| 新增灯泡 | 215 | 46 | 33 |
| 合计 | 3963 | 736 | 33 |

原始旧数据目录保持不变；三类目录通过硬链接复用图片，标签独立保存。对全部图片解码像素做 SHA256 去重，优先保留既有验证集，避免完全重复图片跨训练／验证集。灯泡还按 64 位 dHash 距离不大于 4 分组，同组保持同一数据划分。该办法降低近重复泄漏，不能证明所有相似场景均已隔离。

33 张测试图片仅包含新增灯泡类别；旧类别的评估沿用既有验证集，因此不能将灯泡测试结果称为三个类别共同的独立测试结果。完整图片 ID、划分、像素哈希和标注来源保存在数据集 `manifest.json`。

额外交集审计使用 `scripts/audit_drone_fire_bulb_dataset.py`，结果保存在 `deploy_export/weights/dnb26_drone_fire_bulb_dataset_audit.json`：候选训练集 3963 张与原始验证集 691 张之间，解码像素完全重复为 0 对；64 位 dHash 距离不大于 4 的相似图片为 16 对，涉及 10 张验证图、14 张训练图。原始旧训练集与旧验证集本来存在 4 对完全重复及 20 对 dHash 相似图。dHash 是视觉相似性筛查，不等于已确认来源相同；目前也没有完整场景 ID 或视频序列 ID 可用于全量分组。

候选初始化自旧模型权重，因此移除本轮训练集重复图不能消除初始化权重此前接触过这些图片的影响。旧类的新旧指标用于相同验证集上的配对比较，不宣称独立留出性能。新增灯泡的留出结果单独报告。

新增灯泡测试集对全部训练图检查，完全重复为 0 对、dHash 相似为 1 对；灯泡验证集对应为 0 对与 3 对。这 4 对相似性标记经逐对图像查看，均为灯泡照片与沙漠背景无人机照片之间的 dHash 碰撞，画面场景明显不同；没有发现灯泡图之间距离不大于 4 的跨划分邻居。审计文件单独记录人工查看范围，保留自动筛查的原始计数。

## 复现

```powershell
.\.venv\Scripts\python.exe scripts/build_drone_fire_bulb_dataset.py --sample-mb 768 --bulb-limit 600 --workers 12 --output data/datasets/drone_fire_bulb_v2
.\.venv-train-bulb\Scripts\python.exe scripts/train_drone_fire_bulb_yolo.py --epochs 30 --imgsz 640 --batch 8 --workers 0
```

构建程序拒绝覆盖已有输出目录。训练使用独立 CUDA 环境，避免变更服务端 Python 环境：Python 3.12.13、PyTorch 2.7.1+cu128、torchvision 0.22.1+cu128、Ultralytics 8.4.89，硬件为 RTX 4060 Laptop GPU 8 GiB。

训练从原双类最佳权重初始化，使用三类检测头、AdamW、固定种子 26、640 像素输入和 batch 8。原 `.pt`、`.onnx` 文件保留供回退。训练脚本先在原验证集上评估双类基线，再训练和评估三类候选，并导出 ONNX。

首次运行使用 4 个 DataLoader worker，Windows 在第 5 轮因主机内存分配失败而中断。随后从已保存的 `last.pt` 恢复，改用 `workers=0`；恢复事件与 checkpoint 哈希记录在元数据中。训练环境与服务环境保持独立，不调整系统分页文件或全局 Python 配置。

## 基线与结果文件

相同 640 像素设置下，原双类模型的验证结果如下：

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| 无人机 | 0.8624 | 0.7284 | 0.8078 | 0.3897 |
| 灭火器 | 0.8536 | 0.8425 | 0.8715 | 0.5873 |

训练后的实际结果、权重 SHA256、训练环境和导出结果以 `deploy_export/weights/dnb26_drone_fire_bulb_yolo11n_metadata.json` 为准。该文件训练过程中先记录基线；仅当包含 `checkpoint`、`validation`、`held_out_bulb_test` 字段时，才表示候选训练和评估已完成。`onnx` 字段表示导出也已完成。

最终审计还记录 `training`（实际完成轮数及最佳验证轮次）、`candidate_original_validation`（候选模型在原始双类验证集上的结果）和 `same_split_comparison`（相同验证集、相同输入尺寸下的新旧模型逐类差值）。去重后的三类验证集与原始双类验证集样本不同，应使用后一项比较旧类别变化。`onnx_validation` 同时给出 ONNX 图检查、输入输出尺寸和与 PyTorch 的确定性输入数值比较结果；导出成功与数值比较通过分别记录。

若训练及导出已完成，但最终审计被中断，可单独继续：

```powershell
.\.venv-train-bulb\Scripts\python.exe scripts/train_drone_fire_bulb_yolo.py --finalize-only --imgsz 640 --batch 8 --workers 0
```

此模式核对已发表权重 SHA256，补齐相同分割评估及训练轮数，不覆盖模型权重。

拟交付模型为 `deploy_export/weights/dnb26_drone_fire_bulb_yolo11n_best.pt`，其类别固定为以上三类。通用 `models/yolo11n.pt` 保持独立，提供 COCO 80 类（包括人、车辆）；将两者的检测结果合并展示，不把自定义类别误映射成通用类别。

## 本次实际完成结果

本次共完成 30 轮，最佳训练验证轮次为第 30 轮。以下是复制最佳权重后重新运行验证的结果，输入尺寸为 640 像素；P/R 为 Ultralytics 验证程序报告的工作点，并非线上固定置信度阈值 0.4 下的实测值。

| 三类验证集（736 张） | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| 无人机 | 0.9130 | 0.7560 | 0.8356 | 0.4034 |
| 灭火器 | 0.8761 | 0.8667 | 0.8990 | 0.6243 |
| 灯泡 | 0.6312 | 0.4966 | 0.5208 | 0.2827 |
| 三类平均 | 0.8068 | 0.7064 | 0.7518 | 0.4368 |

灯泡留出测试集包含 33 张图片、51 个标注框：Precision 为 0.6665，Recall 为 0.5294，mAP50 为 0.5727，mAP50-95 为 0.3007。该结果表明新增类别已经具备识别能力，同时约一半标注灯泡在该工作点仍被漏检；需要补充实际展示图片与摄像头环境数据后再提高可靠性。

在原始旧验证集的配对比较中，无人机 mAP50 从 0.8078 提高到 0.8368，mAP50-95 从 0.3897 提高到 0.4041；灭火器分别从 0.8715 提高到 0.8991、从 0.5873 提高到 0.6238。这些结果受上述旧数据重复及初始化曝光限制。

| 成品 | 文件大小 | SHA256 |
| --- | ---: | --- |
| `dnb26_drone_fire_bulb_yolo11n_best.pt` | 5,451,994 字节 | `2e9c68ed57e4f2f3fe56f7dd78a16c0b7b8795d7776dc357fdbb1d2f4a9f32a2` |
| `dnb26_drone_fire_bulb_yolo11n_best.onnx` | 10,566,326 字节 | `387debc31022f7a32001563e30beb8f02ee52d47949941e7710595439eef2c5a` |

ONNX 的输入为 `images`、float32、`[1,3,640,640]`，输出为 `output0`、float32、`[1,7,8400]`。ONNX 图检查通过；固定随机输入下，ONNX Runtime CPU 与 PyTorch 的最大绝对差值为 0.0005341，在 `rtol=0.001, atol=0.001` 下通过比较。

已在 Orange Pi AIpro 20T 使用 ATC 编译为 `Ascend310B4` OM，精度模式为 `allow_fp32_to_fp16`。成品 `dnb26_drone_fire_bulb_yolo11n_best.om` 的 SHA256 为 `b1305d503ca7e363e88d417ae766b38b729d9e3436c780f27f137f4dd2716828`，同名 `.json` 提供类别元数据。35 张板端标注图片检查在固定置信度 0.5、IoU 0.5 下，灯泡 TP=23、FP=7、FN=28，P=0.7667、R=0.4510；平均检测耗时 48.09 毫秒，含预后处理、不含读图。这是 OM 的固定阈值运行检查，不能与上表的完整验证集 mAP 等同。原始报告保存在本地 `output/edge/verification/npu-custom3-verification.json` 和板端 `shared/npu-custom3-verification.json`。

## 应用限制

- Open Images 的灯泡图片包含裸灯泡、包装灯泡和部分发光灯具区域，实际用于“展示灯泡图片触发开灯”的效果需另行实景验证。
- 少量目标类别可能出现在其他来源图片背景中，当前没有对全部旧图和 Open Images 新图进行三类穷尽重标。
- 灯泡图片样本数有限，不能用本次指标推断所有真实灯具、屏幕翻拍和照明条件下的识别效果。
- 灯泡联动需要连续稳定检测、冷却和硬件回执；模型检测到目标本身不代表物理灯已经开启。

三类完整模型包位于 `share/dnb26_drone_fire_bulb_model_package.zip`，含 PT、ONNX、Ascend OM、类别 JSON、训练/审计记录和 SHA256 清单。模型包不含训练图像或现场人脸数据。
