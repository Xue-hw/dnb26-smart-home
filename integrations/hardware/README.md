# 双 UNO 硬件整合

本目录保存硬件组交付、整合固件和电脑 USB 转发程序。当前整合固件已烧录两块 UNO，香橙派已部署真实 gateway 后端与 2.1.0 网页；2.1.0 APK 已生成，实体手机待联调。

| 目录 | 内容 |
| --- | --- |
| `original/` | 原交接文档与两份原始 `.ino`；`import-manifest.json` 记录导入文件的 SHA256 |
| `firmware/Uno1_Environment_Garage/` | UNO1 环境、灯光、风扇、键盘、语音、OLED 和入户门整合固件 |
| `firmware/Uno2_RFID_Door/` | UNO2 RFID、蜂鸣器和车库门整合固件；有效卡读卡成功放行，读取失败拒绝，不输出卡号 |
| `firmware/libraries/` | 共用有界串口协议与持久配置工具 |
| `gateway/client.py` | 电脑侧 USB → HTTP(S) 网关，显式指定串口并核验 UNO 身份 |

接线、控制规则、扩展、编译与联调步骤见 [硬件整合说明](../../docs/hardware-integration.md)。原始交付保持原样，部署时选择 `firmware/` 下的整合版。
