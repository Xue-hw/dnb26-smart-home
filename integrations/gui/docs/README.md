# DnB26 GUI＋Android 交付包 v1.2.0

交付日期：2026-11-15。版本号沿用应用 1.2.0（versionCode 120），本次为交接整理版。

## 先看这里

- 直接安装：将 `APK/DnB26_v1.2.0_demo.apk` 传到安卓手机安装。
- 电脑预览：完整解压，在 `project` 中双击 `双击打开本地预览.cmd`，需要 Node.js。
- 修改源码：打开 `project`，见 `02_构建与排错.md`。
- 后端联调：先看 `03_接口联调清单.md`，再看 project/docs/GUI_API_CONTRACT.md 和 project/src/types/contracts.ts。

## 当前状态

- GUI A1–A4、C1–C6、B5 已实现；B1–B3 预留明确展示区域与接口扩展点；B4 留待增强。
- 网页与 Android 共用 React/TypeScript GUI；含预构建 dist、本地预览、响应式手机布局和 Capacitor Android 工程。
- 包内 APK 为用户在 Windows 构建并上传的原始安装包，本次仅改交付文件名，未重新签名、未修改 APK。
- 构建截图显示 BUILD SUCCESSFUL，112 个任务执行；用户随后确认“手机上测试没问题”。未获手机型号、系统版本或逐项测试记录，不能视为所有机型和全部功能已验收。
- APK 默认使用本机模拟数据；真实后端、硬件、人脸、YOLO、自动温控和照片落盘仍需联调。
- 未部署在线网址。网页 PWA 资源仍保留；安卓 APK 内嵌网页资源，不依赖在线网址。

## 包内容

| 路径 | 用途 |
|---|---|
| APK/ | 可安装的安卓演示 APK |
| project/src/ | GUI 源码与 Mock/HTTP 适配器 |
| project/dist/ | 已构建的网页静态资源 |
| project/android/ | Android 工程、Gradle Wrapper |
| project/docs/ | 接口契约、既有实现及验证记录 |
| 01_完成内容与边界.md | 本轮工作范围与未完成事项 |
| 02_构建与排错.md | 环境、生成 APK、下载及权限排错 |
| 03_接口联调清单.md | 搭档下一步联调顺序 |
| 04_验证与交付记录.md | 验证依据、APK 信息与整理变更 |
| SHA256SUMS.txt | 包内文件 SHA-256 校验值 |

未打包 node_modules、SDK/JDK、Gradle 下载包、构建缓存、local.properties 或签名私钥，这些由目标电脑安装/生成。首次重新构建需要联网。
