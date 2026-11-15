@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 goto missingnode
where npm >nul 2>nul
if errorlevel 1 goto missingnode
if not defined JAVA_HOME if exist "C:\Program Files\Android\Android Studio\jbr\bin\javac.exe" set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
if not defined ANDROID_HOME if exist "%LOCALAPPDATA%\Android\Sdk" set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
if not defined ANDROID_HOME goto missingsdk
if not defined JAVA_HOME goto missingjava
if not exist "%JAVA_HOME%\bin\javac.exe" goto missingjava
node -e "require('fs').writeFileSync('android/local.properties','sdk.dir='+process.env.ANDROID_HOME.replaceAll(String.fromCharCode(92),'/')+'\n')"
if errorlevel 1 goto failed
if not defined npm_config_cache set "npm_config_cache=%LOCALAPPDATA%\npm-cache-dnb26"
call npm ci
if errorlevel 1 goto failed
if not defined VITE_DATA_MODE set "VITE_DATA_MODE=mock"
call npm run android:sync
if errorlevel 1 goto failed
pushd android
call gradlew.bat assembleDebug --no-daemon
set "BUILD_EXIT=%ERRORLEVEL%"
popd
if not "%BUILD_EXIT%"=="0" goto failed
if not exist "android\app\build\outputs\apk\debug\app-debug.apk" goto failed
echo APK生成成功，输出文件夹即将打开。
explorer "android\app\build\outputs\apk\debug"
pause
exit /b 0
:missingnode
echo 请先安装兼容的Node.js：22.22.2+（22系列）或24.15.0+（24系列）。
goto failed
:missingjava
echo 请安装JDK 21，并设置JAVA_HOME指向JDK目录。也可安装兼容的Android Studio。
goto failed
:missingsdk
echo 未找到Android SDK。请通过Android Studio安装SDK 35，或设置ANDROID_HOME。
goto failed
:failed
echo 未生成APK。请保留本窗口的错误信息，勿把源码ZIP当作安装包。
pause
exit /b 1
