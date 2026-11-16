> 当前整合版本为 2.0.0，默认连接真实后端。新增实时识别、系统报警和运行时连接配置，详见 [系统整合说明](docs/SYSTEM_INTEGRATION.md)。历史交付说明保留作为参考。

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

当前整合版为2.1.0 / versionCode210，浅色控制台与3D房屋视图；Web/Capacitor APK共用服务，实体手机按 docs/联调测试表.md 复验。
