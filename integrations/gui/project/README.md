# DnB26 智慧家 GUI / Android v1.2.0

本工程用于课程智能家居GUI，React＋TypeScript＋Vite＋ECharts，Capacitor 7 封装Android。

交付包上一级的 README.md 和 01–04 说明为本次最新交接入口。安装包位于 ../APK/，由用户Windows构建并确认手机测试通过。默认模拟模式，真实后端和硬件仍待联调；未部署在线网址。

## 电脑预览

完整解压，双击“双击打开本地预览.cmd”。使用预构建dist，需Node.js。

## 开发

建议Node22.22.2+（22系列）或24.15.0+（24系列）。运行npm ci，然后npm run dev。

验证命令：npm run typecheck、npm run lint、npm test、npm run build。

## Android

阅读 ANDROID_README.md。生成演示APK可双击“生成安卓APK.cmd”；真实模式配置见上一级03_接口联调清单.md。

## 文档

- 使用说明.md：用户操作。
- docs/GUI_API_CONTRACT.md：接口契约。
- docs/V1_1_INTEGRATION.md：A/B/C工作范围和联调约定。
- docs/GUI_ACCEPTANCE.md：验证记录。

本版仍使用1.2.0 / versionCode120；交接整理没有增加应用功能版本。
