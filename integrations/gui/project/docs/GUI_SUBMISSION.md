> v1.1.0更新：本包根目录包含源码和dist，无需寻找旧版本release压缩包。检查记录以GUI_ACCEPTANCE.md为准。

# GUI 提交与版本规范

## 1. 源码包

应包含：`src/`、`public/`、`docs/`、`deploy/`、配置文件、`.env.example`、`package.json`、`package-lock.json`、README 和 CHANGELOG。

不应包含：

- `node_modules/`、开发日志、系统缓存、个人 IDE 配置。
- 个人电脑绝对路径、账号、令牌或密钥。
- 真实授权人员照片、人脸特征或业务数据库。
- 旧平台构建输出、临时截图和未引用原型。

## 2. 静态发布包

发布包以 `dist/` 为核心，并附：

- `docs/GUI_DEPLOY.md`
- `docs/GUI_API_CONTRACT.md`
- `docs/GUI_ACCEPTANCE.md`
- `deploy/nginx.conf.example`
- `CHANGELOG.md`
- `SHA256SUMS.txt`

部署只需 dist 内文件，其他内容是交接与验收材料，不必复制到 Web 根目录。

## 3. 版本号

格式：`gui-v主版本.次版本.修订号`。

- 主版本：接口或页面结构不兼容变化。
- 次版本：新增页面、接口或功能，保持兼容。
- 修订号：视觉、文案、错误修复。

每次提交更新 CHANGELOG，注明数据模式、接口契约版本、验证环境和已知限制。不要只用“最终版”“最新版”。

## 4. 提交前检查

```bash
npm ci
npm run typecheck
npm run lint
npm run build
```

并检查：

- 四个业务页和接口测试页均可打开。
- Mock 模式全部接口测试通过。
- 设备控制、人员增删、历史筛选和识别演示可操作。
- 1440px、1024px、390px 三档宽度无横向溢出。
- 无公网字体、图片和 favicon 请求。
- 生产 API 默认同源，无 localhost 硬编码。
- Mock 推理、摄像头占位、人脸接口占位均有明显说明。
- dist 可由普通静态服务器运行，刷新子路由不 404。

## 5. 联调提交

GUI 同学提交契约与 HTTP Adapter；后端同学返回接口实现差异；硬件字段变化由后端统一整理。真实设备写命令不得随普通 GUI 只读联调自动测试，必须在明确硬件测试环境中单独验收。
