@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem Silver Pines - 主角换成奶蛙（安装）：主资源包 + 补丁资源包（举枪/换弹/手臂等）
rem 游戏不在 D:\Games\Silver Pines 时：把游戏文件夹拖到本文件上，或设置环境变量 SILVER_PINES
set "GAME=D:\Games\Silver Pines"
if defined SILVER_PINES set "GAME=%SILVER_PINES%"
if not "%~1"=="" set "GAME=%~1"
set "AA=%GAME%\Carpenter_Data\StreamingAssets\aa"
set "SW=%AA%\StandaloneWindows64"
set "BUNDLE=team17_auto_base_characters_compressed_assets_player.bundle"
set "HERE=%~dp0"
set "LIST=%HERE%build\patches\bundles.txt"

if not exist "%SW%\%BUNDLE%" goto :no_game
tasklist /FI "IMAGENAME eq Carpenter.exe" | "%SystemRoot%\System32\find.exe" /I "Carpenter.exe" >nul
if not errorlevel 1 goto :running
if not exist "%HERE%build\%BUNDLE%" goto :no_build
if not exist "%LIST%" goto :no_build

if not exist "%HERE%backup\patches" mkdir "%HERE%backup\patches"
if not exist "%HERE%backup\%BUNDLE%" (
  copy /Y "%SW%\%BUNDLE%" "%HERE%backup\%BUNDLE%" >nul || goto :fail
)
if not exist "%HERE%backup\catalog.bin" (
  copy /Y "%AA%\catalog.bin" "%HERE%backup\catalog.bin" >nul || goto :fail
)
for /f "usebackq delims=" %%F in ("%LIST%") do (
  if not exist "%HERE%backup\patches\%%F" copy /Y "%SW%\%%F" "%HERE%backup\patches\%%F" >nul || goto :fail
)
echo 原版文件已备份到 %HERE%backup

copy /Y "%HERE%build\%BUNDLE%" "%SW%\%BUNDLE%" >nul || goto :fail
set /a N=0
for /f "usebackq delims=" %%F in ("%LIST%") do (
  copy /Y "%HERE%build\patches\%%F" "%SW%\%%F" >nul || goto :fail
  set /a N+=1
)
echo 安装完成！（主资源包 + %N% 个补丁资源包）启动游戏后主角就是奶蛙了。
pause
exit /b 0

:no_game
echo 找不到游戏文件：%SW%\%BUNDLE%
echo 游戏不在 D:\Games\Silver Pines 的话，把游戏文件夹（里面有 Carpenter.exe）拖到这个 bat 文件上。
pause
exit /b 1

:running
echo 游戏正在运行，请先退出 Silver Pines 再安装。
pause
exit /b 1

:no_build
echo 还没有生成奶蛙资源包（%HERE%build），请先按 README 运行 scripts\frogify.py。
pause
exit /b 1

:fail
echo 复制失败（文件被占用或没有权限）。已复制的文件可以用 restore_original.bat 还原。
pause
exit /b 1
