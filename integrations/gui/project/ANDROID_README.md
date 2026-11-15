# Android v1.2.0 当前状态

2026-11-15：用户在Windows通过assembleDebug构建，截图显示BUILD SUCCESSFUL；上传原APK已包含在交付包 ../APK/，用户确认手机测试正常。具体机型/系统与逐项测试记录未提供。

应用：DnB26 智慧家；包名com.dnb26.smarthome；versionName1.2.0；versionCode120；minSdk23；target/compileSdk35。

详细环境、构建、下载超时、缓存EPERM、签名注意事项见 ../02_构建与排错.md；后端连接见 ../03_接口联调清单.md。

APK内嵌网页资源，默认mock，不需要在线网址。原生模式隐藏PWA安装入口，不注册网页Service Worker；返回键优先关闭弹窗，子页面返回，首页回到后台。真实硬件、人脸、YOLO、自动控温和照片存储仍由后端/硬件提供，当前未完成联调。

目标电脑自行配置JAVA_HOME / ANDROID_HOME，不共享local.properties或签名私钥。当前Wrapper采用官方Gradle8.11.1-bin URL及120秒网络超时；本地ZIP备用方案见排错说明。

可选GitHub Actions工作流未触发验证，未上传仓库或部署在线网址。当前演示APK不是应用商店发行包。
