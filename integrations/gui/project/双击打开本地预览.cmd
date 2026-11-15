@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title DnB26 GUI 本地预览

if not exist "dist\index.html" (
  echo [错误] 未找到 dist\index.html。
  echo 请先运行 npm run build，或使用包含 dist 的香橙派部署包。
  echo.
  pause
  exit /b 1
)

set "NODE_EXE="
where node >nul 2>nul && set "NODE_EXE=node"
if not defined NODE_EXE if exist "C:\Program Files\nodejs\node.exe" set "NODE_EXE=C:\Program Files\nodejs\node.exe"

if not defined NODE_EXE (
  echo [错误] 未检测到 Node.js。
  echo 请安装 Node.js 22.12+，然后重新双击本文件。
  echo.
  pause
  exit /b 1
)

"%NODE_EXE%" "scripts\preview-server.mjs"
if errorlevel 1 (
  echo.
  echo 预览启动失败，请查看上方错误信息。
  pause
)

endlocal
