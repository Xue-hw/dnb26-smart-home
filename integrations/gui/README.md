# DnB26 GUI 交付包

GUI 位于 `project/`，交付说明位于 `docs/`。这是 React 19、TypeScript、Vite 和 Capacitor Android 工程，页面覆盖仪表盘、历史数据、设备控制、监控和人员管理。

## 当前边界

- 默认数据源是 Mock；切换真实模式后通过 HTTP API 访问后端。
- GUI 不直接访问 GPIO、串口、MQTT、摄像头或 YOLO/人脸模型。
- `project/docs/GUI_API_CONTRACT.md` 是后续与现有后端联调的主要接口依据。
- 本次按用户确认只上传源码和文档；已构建的 `dist/`、APK 没有纳入仓库。

## 本地检查

```powershell
cd integrations/gui/project
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

Orange Pi 部署时可将构建后的 `dist/` 交给 Nginx 提供局域网 Web GUI；本目录中的 Android 工程用于需要 APK 时重新构建。

本次验证结果：`npm run typecheck`、`npm run lint`、`npm test` 和 `npm run build` 全部通过。`npm audit` 当前报告 8 项 moderate 依赖风险，主要涉及 ECharts、`typescript-eslint` 和 `minimatch`；正式发布前应按兼容性评估升级方案。
