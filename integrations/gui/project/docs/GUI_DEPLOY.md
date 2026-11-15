> v1.1.0更新：本包根目录包含源码和dist，无需寻找旧版本release压缩包。检查记录以GUI_ACCEPTANCE.md为准。

# 香橙派 GUI 静态部署说明

本交付只负责 GUI。香橙派上的 FastAPI、数据库、模型和硬件服务由同组其他同学部署；本 GUI 默认 Mock 模式时甚至可以完全脱离这些服务运行。

## 1. 在 PC 上构建

要求 Node.js 22.12 或更高版本：

```bash
npm ci
npm run typecheck
npm run lint
npm run build
```

得到 `dist/`。默认构建为 Mock 演示版。若接真实后端，在构建前准备 `.env.production`：

```text
VITE_DATA_MODE=http
VITE_API_BASE_URL=
```

注意：环境变量会被编译进静态 JS，修改后必须重新构建；不要在环境变量中放账号密码或密钥。

## 2. 复制到香橙派

将 `dist/` 内所有文件复制到 `/var/www/dnb26-gui/`。例如在同组已配置好的部署流程中使用 SCP 或 U 盘复制，目标机器只需要静态文件和 Nginx。

建议目录：

```text
/var/www/dnb26-gui/
├─ index.html
├─ assets/
├─ demo/
└─ favicon.svg
```

不需要复制 `node_modules`、`src` 或开发日志到 Web 根目录。

## 3. 配置 Nginx

参考 `deploy/nginx.conf.example`：

- `/` 使用 `try_files $uri $uri/ /index.html`，保证刷新 `/monitor` 等子路由不 404。
- `/api/` 与 `/uploads/` 转发到 `127.0.0.1:8000`。
- `/api/stream` 关闭代理缓冲，适配 SSE。
- `index.html` 不缓存，带哈希的 assets 可长缓存。

修改配置后先执行 `nginx -t`，通过后再 reload。实际启用配置和开放端口由负责香橙派系统的同学执行。

## 4. 访问与验收

- 本机：`http://<香橙派IP>/`
- 手机或电脑与香橙派处于同一局域网。
- 默认 Mock 版不需要后端即可操作。
- HTTP 版若后端未启动，页面应显示连接错误，不应继续伪装实时在线。
- 断网环境下字体、favicon、演示场景和摄像头占位图仍可显示。

## 5. 常见问题

### 手机能打开页面，但接口请求失败

检查构建时是否误把 `VITE_API_BASE_URL` 填成 `localhost`。手机上的 localhost 是手机自身。同源部署应保持该变量为空，由 Nginx 代理。

### 首页能打开，刷新子路由 404

检查 Nginx 是否包含 `try_files $uri $uri/ /index.html`。

### 页面更新后仍是旧版本

确认复制的是新 dist 的全部内容，并保留 `index.html` 的 no-cache 配置；必要时强制刷新浏览器。

### SSE 一直等待

检查 `/api/stream` 是否关闭 `proxy_buffering`，后端是否按命名事件发送 data JSON。SSE 未接好时 GUI 仍通过 30 秒轮询更新。

### 仅静态演示是否还需要 FastAPI

不需要。默认 Mock 版所有接口在浏览器内实现；只有设置 `VITE_DATA_MODE=http` 后才需要后端。

## 6. 回滚

保留上一版本的完整 dist 目录。回滚时整体替换 Web 根目录，避免新旧哈希资源混用。GUI 回滚不影响后端数据库，但接口契约如有变化，应同时核对前后端版本。
