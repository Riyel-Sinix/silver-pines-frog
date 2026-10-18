@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem Silver Pines - 恢复原版主角（主资源包 + 所有备份的补丁资源包）
rem 游戏不在 D:\Games\Silver Pines 时：把游戏文件夹拖到本文件上，或设置环境变量 SILVER_PINES
set "GAME=D:\Games\Silver Pines"
if defined SILVER_PINES set "GAME=%SILVER_PINES%"
if not "%~1"=="" set "GAME=%~1"
set "AA=%GAME%\Carpenter_Data\StreamingAssets\aa"
set "SW=%AA%\StandaloneWindows64"
set "BUNDLE=team17_auto_base_characters_compressed_assets_player.bundle"
set "HERE=%~dp0"

if not exist "%SW%\%BUNDLE%" goto :no_game
tasklist /FI "IMAGENAME eq Carpenter.exe" | "%SystemRoot%\System32\find.exe" /I "Carpenter.exe" >nul
if not errorlevel 1 goto :running
if not exist "%HERE%backup\%BUNDLE%" goto :no_backup

copy /Y "%HERE%backup\%BUNDLE%" "%SW%\%BUNDLE%" >nul || goto :fail
if exist "%HERE%backup\catalog.bin" copy /Y "%HERE%backup\catalog.bin" "%AA%\catalog.bin" >nul || goto :fail
if exist "%HERE%backup\patches\" (
  for %%F in ("%HERE%backup\patches\*.bundle") do (
    copy /Y "%%F" "%SW%\%%~nxF" >nul || goto :fail
  )
)
echo 已恢复原版主角。
pause
exit /b 0

:no_game
echo 找不到游戏文件：%SW%\%BUNDLE%
echo 游戏不在 D:\Games\Silver Pines 的话，把游戏文件夹（里面有 Carpenter.exe）拖到这个 bat 文件上。
pause
exit /b 1

:running
echo 游戏正在运行，请先退出 Silver Pines。
pause
exit /b 1

:no_backup
echo 没有找到备份（%HERE%backup），可能还没安装过奶蛙。
pause
exit /b 1

:fail
echo 复制失败（文件被占用或没有权限）。
pause
exit /b 1
