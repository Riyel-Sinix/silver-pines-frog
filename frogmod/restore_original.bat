@echo off
setlocal EnableExtensions
rem Silver Pines frog mod - uninstall: puts back the main bundle, every backed-up patch bundle, catalog.bin and
rem globalgamemanagers. If the game is not in D:\Games\Silver Pines: drag the game folder onto this file, or
rem set SILVER_PINES. All logic stays ASCII; the code page is switched only to print the messages (see install).
set "GAME=D:\Games\Silver Pines"
if defined SILVER_PINES set "GAME=%SILVER_PINES%"
if not "%~1"=="" set "GAME=%~1"
set "AA=%GAME%\Carpenter_Data\StreamingAssets\aa"
set "SW=%AA%\StandaloneWindows64"
set "GGM=%GAME%\Carpenter_Data\globalgamemanagers"
set "BUNDLE=team17_auto_base_characters_compressed_assets_player.bundle"
set "HERE=%~dp0"
set "MSG=fail"

if not exist "%SW%\%BUNDLE%" (set "MSG=no_game" & goto :show)
tasklist /FI "IMAGENAME eq Carpenter.exe" | "%SystemRoot%\System32\find.exe" /I "Carpenter.exe" >nul
if not errorlevel 1 (set "MSG=running" & goto :show)
if not exist "%HERE%backup\" (set "MSG=no_backup" & goto :show)

if exist "%HERE%backup\%BUNDLE%" copy /Y "%HERE%backup\%BUNDLE%" "%SW%\%BUNDLE%" >nul || goto :show
if exist "%HERE%backup\catalog.bin" copy /Y "%HERE%backup\catalog.bin" "%AA%\catalog.bin" >nul || goto :show
if exist "%HERE%backup\patches\" (
  for %%F in ("%HERE%backup\patches\*.bundle") do (
    copy /Y "%%F" "%SW%\%%~nxF" >nul || goto :show
  )
)
rem globalgamemanagers is put back only when the size matches: after a game update the old copy must not return
set "MSG=done"
if not exist "%HERE%backup\globalgamemanagers" goto :restored
for %%A in ("%GGM%") do set "SZ_GAME=%%~zA"
for %%A in ("%HERE%backup\globalgamemanagers") do set "SZ_BAK=%%~zA"
if not "%SZ_GAME%"=="%SZ_BAK%" goto :restored
copy /Y "%HERE%backup\globalgamemanagers" "%GGM%" >nul || (set "MSG=fail" & goto :show)

:restored
rem files that were already the mod's when this folder installed it have no backup (see install_frog.bat)
if exist "%HERE%backup\no_original.txt" set "MSG=done_partial"

:show
chcp 65001 >nul
goto :msg_%MSG%

:msg_done
echo 已恢复原版主角。
pause
exit /b 0

:msg_done_partial
echo 已恢复备份里的原版文件。
echo 安装时有些文件已经是旧版 mod 的，没有原版备份（清单在 backup\no_original.txt）。
echo 请在 Steam 里对 Silver Pines「验证游戏文件的完整性」，把它们也恢复成原版。
pause
exit /b 0

:msg_no_game
echo 找不到游戏文件：
echo   %SW%\%BUNDLE%
echo 游戏不在 D:\Games\Silver Pines 的话，把游戏文件夹（里面有 Carpenter.exe）拖到这个 bat 文件上。
pause
exit /b 1

:msg_running
echo 游戏正在运行，请先退出 Silver Pines。
pause
exit /b 1

:msg_no_backup
echo 没有找到备份（这个文件夹里的 backup 文件夹），可能还没安装过奶蛙。
pause
exit /b 1

:msg_fail
echo 复制失败（文件被占用或没有权限）。
pause
exit /b 1
