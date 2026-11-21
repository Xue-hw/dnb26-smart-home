# UI 设计审阅：温暖极简

记录日期：2026-11-17。阶段：用户已审阅通过，批准将新 UI 纳入远程仓库的共享前端源码；现场部署另行安排。

## 审阅入口

- 可交互预览：<http://127.0.0.1:8002/>。由本机 Vite 提供，默认使用独立 Mock 数据。
- 六页截图画廊：[打开本机画廊](../output/ui-review/index.html)。包含桌面与手机尺寸截图，以及人员弹窗。
- 浏览器工程核验：[visual-qa.json](../output/ui-review/visual-qa.json)。

预览地址和 `output/` 链接均为本机审阅资源，截图及工程核验产物未纳入远程源码仓库。

用户可在预览中切换首页、监控识别、历史、人员、系统和接口页面，检查布局与现有交互。手机尺寸截图来自本机 Edge 响应式窗口；新版 UI 尚未安装到实体 APK。线上网页与已安装 APK 继续使用 2.1.7 的原界面。

预览服务停止后，可在本地 PowerShell 重新启动：

```powershell
Set-Location 'D:\Codework\dnb26-smart-home\integrations\gui\project'
$env:VITE_DATA_MODE = 'mock'
npm run dev -- --host 127.0.0.1 --port 8002 --strictPort
```

## 设计方向

用户已选定“温暖极简：便当盒布局＋自然材质配色”。本次使用 `frontend-design` 技能，参考 Interface Atlas 的以下内容：

- [风格目录](https://atlas.gongfpp.icu/styles)
- [Bento Grid](https://atlas.gongfpp.icu/styles/bento-grid)：分区网格、统一间距、随屏幕重排。
- [Organic](https://atlas.gongfpp.icu/styles/organic)：暖白、苔绿和陶土色，衬线标题与清晰正文。
- [Minimalism](https://atlas.gongfpp.icu/styles/minimalism)：克制的装饰、明确的内容层级。

保留“栖居”品牌和现有 3D 房屋。桌面使用浅绿侧栏与深绿选中状态，温度、湿度和灯光采用不同的自然色卡片。手机使用两列指标、跨列风扇卡片与底部六项导航。六页统一面板、表单、按钮、状态和弹窗的间距与形状。字体使用设备现有字体，不新增外部字体或运行时图片请求。

## 代码范围与功能保持

相对改版前快照，生产源码仅改动三个文件：

| 文件 | 变更 |
| --- | --- |
| `integrations/gui/project/src/atlas-theme.css` | 新增共享主题覆盖层，原 `styles.css` 保留 |
| `integrations/gui/project/src/main.tsx` | 追加主题样式导入 |
| `integrations/gui/project/src/components/Layout.tsx` | 增加导航说明和键盘跳转到主要内容的入口 |

设备命令、权限恢复、连接保存、路由、人脸与活体规则、识别阈值、媒体获取、历史查询及后端逻辑保留。识别框的通用、专用、人脸与通行状态颜色和文字继续使用原有定义。新增样式保持危险、警告、成功及禁用状态可区分，并恢复原样式隐藏的设备状态标签。

## 本地核验

- `npm run build`：通过，包含 TypeScript 检查。
- `npm run lint`：通过。
- `npm test`：完整通过，包含 40 个集成场景及权限保存、刷新、媒体、拖放和录入状态回归。
- Edge 真实浏览器：1440、768、390、320 像素宽度各检查六页，共 24 组；无文档横向溢出、无按钮文字裁剪，六个导航入口可达。
- 原有 Mock 灯开关、模拟回执、设备分类筛选、人员弹窗初始焦点与 Escape 关闭通过。
- 手机尺寸键盘跳转后主标题未被顶栏遮挡；1024×600、1366×600 下侧栏可滚动触达“手机使用”与状态。
- 浏览器核验记录无运行时异常，预览未产生远程 HTTP 请求。
- React 与代码只读审查已完成。审查发现的筛选文字、占位文字、预览说明和底部导航文字对比度已加深；语义状态颜色保留。

过程中的首轮标题预期和第三轮新增人员按钮选择器有误，修正核验脚本后通过；第二轮发现 320 像素宽度加系统滚动条时根元素横向溢出，已修改主题的 `html/body min-width` 并复验通过。早期核验记录保留在截图目录。

这些结果用于本地界面工程核验，没有新增正式现场验收结论。用户已要求其它验收工作收工，原测试表的待测、跳过及未通过范围保持。

审查期间发生过一次范围偏离：审查代理读取了线上系统状态和快照、安装包元信息，并将已安装 APK 带到前台；未读取人员或摄像头图像，未部署、安装、清数据、改配置或发送设备命令。该操作已停止，临时 ADB 转发已移除；应用可能恢复原有自动连接与轮询。

## 备份与发布状态

改版前源码快照已推送到现有远程分支 `codex/system-integration`：

- 提交：[e1afb132ccf4fa5bab997a2675ec6a2568c91093](https://github.com/Xue-hw/dnb26-smart-home/commit/e1afb132ccf4fa5bab997a2675ec6a2568c91093)
- 本地源码包：[DnB26_v2.1.7_source_e1afb13.zip](../output/backups/DnB26_v2.1.7_source_e1afb13.zip)
- SHA256：`310153a88e532394b85bd04b721ea3258aeda0c298d4d1e50cc48fc12d4e1784`

备份包含当前源码与文档，排除运行凭据、数据库、人员图像和特征、模型权重及生成缓存；没有删除远程原有历史。用户原有文档修改已随快照保留。

用户已审阅并批准以这版 UI 替换远程仓库中的原界面。发布沿用现有 `codex/system-integration` 分支，新主题通过 `main.tsx` 默认加载，覆盖电脑网页与 APK 共用的界面样式；原功能和业务行为保留。改版前快照 `e1afb13` 保留，可用于比较或回退。

本次范围为源码提交与远程推送。尚未同步 Android 资源、生成新版 APK、覆盖安装或更新板端网页；线上版本继续使用原有 2.1.7 界面。正式联调测试表保持原有收口状态。
