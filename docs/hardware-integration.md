# 双 UNO 硬件整合说明

本地代码按硬件组交接文档的实际器件整合：两块 UNO 通过 USB 接电脑，电脑在局域网中转至香橙派；香橙派运行数据库、视觉推理和 HTTP API，电脑浏览器与 Android APK 共用 API。当前整合固件已烧录（UNO1：COM10，UNO2：COM9），后端已部署并启用真实 gateway 模式。USB 网关在电脑后台运行；电脑与香橙派均需保持开机及局域网连通。

## 原始交付与真实设备范围

原始交付保存在 `integrations/hardware/original/`，整合版在 `integrations/hardware/firmware/`。导入清单保存两份源码 SHA256，可核验原件保持不变。成员原始 SQL、历史数据、Mock 示例和通用设备类型继续保留。

| 板卡 | 已安装器件 | 本次软件对齐及扩展 |
| --- | --- | --- |
| UNO1 | DHT11、光敏、8 颗 NeoPixel、PWM 风扇 | 温湿度与光照上报、传感器故障；本地温控及阈值同步；手动开关、亮度、灯色、启用灯珠数量、风扇速度与恢复自动 |
| UNO1 | 矩阵键盘、入户门舵机 | 密码开门、错误事件、远程开关门、4 位密码修改、5 秒自动关门 |
| UNO1 | ASRPRO、OLED | 保留本地语音与状态显示；语音事件同步，5 秒覆盖后还原先前设置 |
| UNO2 | RC522、车库门舵机、蜂鸣器 | 有效卡读取放行、读取失败拒绝事件、模块状态、非阻塞舵机、远程开关门、4 位密码修改、5 秒自动关门；保留刷卡蜂鸣提示 |

未安装的窗户、雨滴、烟雾、空调和独立锁，在真实 `gateway` 模式中隐藏；通用代码与演示资料保留。没有新增这些硬件的采集、控制或联动。

两扇门没有门磁或限位开关。上报的 `state_basis=actuator` 表示舵机控制器状态；ACK 表示控制器处理完成。实际是否到位、卡住或关严，需要现场观察，现有代码不能据此检测机械故障。

## 控制规则

- UNO1 本地负责风扇自动温控，默认开启 30°C、关闭阈值 28°C，温度达到或低于关闭阈值停止。后端同步阈值、记录与报警，不重复下发自动开关命令。阈值精度 0.1°C；只有实际状态报告与后端保存值一致时才显示已同步。
- 手动开关、亮度及风扇调速进入手动模式，持续生效；“恢复自动”单独下发 `mode=auto`。颜色和灯珠数量修改保留当前亮度及模式。
- 风扇速度范围 0～100%，映射到 PWM 0～255；默认 40%（PWM 102，原交付固定 PWM 100）。0 表示手动停；此后执行开风扇或恢复自动时，零速度恢复为默认 40%。语音临时开启会在覆盖结束后恢复原速度及模式。这是 PWM 设置，无转速传感器反馈，低档能否稳定转动需现场测试。
- 灯默认颜色 `#FF9628`，默认启用全部 8 颗；可设置颜色与启用数量 1～8。自动亮度仍按光敏原始值：≤500 为 0%，501～800 为 20%，>800 为 60%；数值越大环境越暗。
- 语音灯／风扇指令临时覆盖 5 秒，然后恢复语音之前的模式和手动设置。连续语音延长覆盖时间，保留第一次覆盖前的快照；覆盖期间收到新的远程手动／恢复自动指令，以新指令为准。
- 两扇门开后 5 秒自动关闭，无常开模式；车库平滑运动期间显示 `moving`，禁止用未知或移动状态推断 toggle。
- 两扇门支持修改 4 位数字密码，UNO EEPROM 带版本与校验保存；网页以掩码输入，不读回密码。密码更改命令的公开回执、历史和事件不能包含明文密码。密码经过浏览器→API→电脑→UNO传输，部署使用项目 HTTPS 入口。
- 按最终确认取消 UID 白名单。RC522 实际读卡成功且 UID 长度为 4、7 或 10 字节时允许；读取失败或异常长度拒绝。卡号仅用于读卡协议有效性检查，不输出到串口、不进入新事件、后端历史或 GUI；这项规则不提供持卡人身份授权。
- 键盘、刷卡和语音事件向后端同步；刷卡只记录通过或拒绝，不记录卡号，语音记录有效的 1～6 指令编号。蜂鸣器保留本地刷卡提示用途。

## 网关配置与运行

后端设置 `DNB_HARDWARE_MODE=gateway`，并将独立随机令牌配置为 `DNB_GATEWAY_TOKEN`。电脑网关进程配置相同令牌。管理员令牌 `DNB_API_TOKEN` 用于 GUI 写操作，两者用途分开。私有令牌放进本机进程环境或私有配置，禁止写入仓库。

在仓库根目录安装根 `requirements.txt` 中的依赖后运行。以下命令只列出端口，不打开串口：

```powershell
python -m integrations.hardware.gateway.client --list-ports
```

确认 UNO1 与 UNO2 对应端口后，使用显式端口启动；可只连接其中一块，另一块独立显示离线：

```powershell
python -m integrations.hardware.gateway.client --backend https://192.168.137.2:8443 --ca D:\path\project-certificate.pem --uno1 COM3 --uno2 COM4
```

`--ca` 指向项目证书，保留 TLS 校验。开发 HTTP 入口可指定 `http://192.168.137.2:8080`，不要添加 `--ca`。端口是示例；重新插拔后的端口可能改变，网关会核验响应身份，不会盲目把任意串口当作执行板。Arduino 串口监视器与转发程序不能同时占用同一 COM 端口。开启串口常使 UNO 自动复位，网关等待启动和新状态后才开放控制。

## 串口和 HTTP 协议

USB 串口为 9600 baud。普通调试日志可保留，上行仅解析 `DNB1 ` 前缀的 JSON 行。网关按字节累积跨读取超时的行，溢出整行丢弃；过时遥测不作为新采样重新发送。

```text
ID\n
STATE\n
DNB1 <32位小写十六进制command_id> <OPCODE> [args]\n
```

| 操作码 | 参数 | 板卡 |
| --- | --- | --- |
| `DOOR_OPEN` / `DOOR_CLOSE` | 无 | 对应门所在 UNO |
| `LIGHT_ON` / `LIGHT_OFF` / `LIGHT_AUTO` | 无 | UNO1 |
| `BRIGHTNESS` | 0～100 整数 | UNO1 |
| `LAMP_RGB` | R G B 启用数量，RGB 各 0～255、数量 1～8 | UNO1 |
| `LAMP_COLOR` | R G B，各 0～255，只改颜色 | UNO1 |
| `LAMP_COUNT` | 1～8，只改启用数量 | UNO1 |
| `FAN_ON` / `FAN_OFF` / `FAN_AUTO` | 无 | UNO1 |
| `FAN_SPEED` | 0～100 整数 | UNO1 |
| `TEMP_LIMITS` | 开启温度 关闭温度，最多 1 位小数 | UNO1 |
| `ENTRANCE_PIN` | 4 位数字 | UNO1 |
| `GARAGE_PIN` | 4 位数字 | UNO2 |

上行分为 `identity`、`state`、`ack`、`event`。UNO1 状态包含 `dht_ok`、温湿度、光照、灯开关／亮度／模式／颜色／数量、风扇开关／模式／速度、入户门控制状态和温控阈值；DHT 失败时温湿度为 `null`。UNO2 包含车库控制状态、`rfid_ok`、`rfid_restricted`。身份含 `protocol=1`。

电脑通过专用认证的 `POST /api/hardware/gateway/exchange` 交换状态与命令，每批最多 32KB。进程有独立 session UUID，批次单调递增，每次 USB 连接或 UNO RESET 换 connection ID。同板只派发一个未确认命令，至少间隔 1.1 秒；其它命令仍在后端原 5 秒有效期内排队。客户端统一节流业务、配置及状态查询，健康遥测期间不额外查询。命令只领取一次、有短有效期，丢失 HTTP 响应不会重放开门；已经发送但未确认的命令在连接变化后标记结果未知。相机联动领取前再验证采集会话与 1.5 秒图像年龄。

UNO1／UNO2 分别判断在线，掉线禁用所属设备。DHT 与 RC522 故障独立于板卡在线状态显示并报警。配置 ACK 只确认命令处理，温控配置是否同步依赖后续实际状态。

## 本地编译

便携工具与依赖仅放在 `D:\CodexData\scratch\dnb26-hardware-build`，不改 Windows 全局 Arduino 配置。使用 Arduino CLI 1.6.0、`arduino:avr` 1.8.6、UNO 板型。库版本为 NeoPixel 1.15.5、DHT 1.4.7、Unified Sensor 1.1.15、Servo 1.3.0、U8g2 2.36.19、MFRC522 1.4.12。

```powershell
& 'D:\CodexData\scratch\dnb26-hardware-build\cli\arduino-cli.exe' `
  --config-file 'D:\CodexData\scratch\dnb26-hardware-build\arduino-cli.yaml' `
  compile --fqbn arduino:avr:uno `
  --libraries 'D:\Codework\dnb26-smart-home\integrations\hardware\firmware\libraries' `
  --build-path 'D:\CodexData\scratch\dnb26-hardware-build\build-uno1' `
  --output-dir 'D:\CodexData\scratch\dnb26-hardware-build\output-uno1' `
  'D:\Codework\dnb26-smart-home\integrations\hardware\firmware\Uno1_Environment_Garage'
```

UNO2 将上述 `build-uno1`、`output-uno1` 和固件目录换成对应 UNO2 路径。命令仅编译，不包含 `upload`，不会烧录。编译结果与本地自动检查记录存于忽略的 `output/hardware/`，构建二进制留在 D 盘 scratch。

## 后续现场测试

部署／烧录后逐项验证：身份与端口、两板独立掉线、传感器故障与恢复、温控与手动模式、语音覆盖还原、灯色及灯珠数量、风扇调速、两门动作与 5 秒关闭、密码修改与断电保存、有效／无效 RFID、网关断线与重连不重放，以及实时人脸与灯泡联动。每项在电脑网页和实体手机 APK 上复验。当前本地测试与编译不能替代电机、电源、传感器和手机的现场验证。

## 本轮验证与联调入口

固件编译及回读校验通过；UNO1 Flash 29260/32256、SRAM 1473/2048，UNO2 Flash 11392/32256、SRAM 570/2048。实际身份、DHT11、光照、RC522 状态上报在线，30/28°C 阈值同步确认。灯开关、42%亮度、颜色、3颗灯珠、风扇100%/0%、两门开后自动关闭、阈值修改及还原，已完成控制器 ACK/遥测回归；机械动作需现场确认。曾复测出现连续命令缺ACK，已加入同板排队、写入节流与减少重复查询后复验。

逐项结果以 [联调测试表](联调测试表.md) 为准，手机 APK 与物理观察独立验收。电脑后台网关 PID 记录位于忽略的 `deploy/local/gateway.pid`，重启后从仓库根目录运行 `.venv\Scripts\python.exe deploy/local/run_gateway.py`；关闭 Arduino 串口监视器后再启动，不可同时占用串口。私有令牌文件不进入 Git。
