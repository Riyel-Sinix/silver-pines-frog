@echo off
setlocal EnableExtensions
rem Silver Pines frog mod - install: main bundle + patch bundles (guns, reloads, arms, idle laugh, dialogue and
rem backpack portraits) + one switch in globalgamemanagers that turns on Unity's own audio for the laugh's sound
rem (the game itself plays its sound through FMOD and is not affected).
rem If the game is not in D:\Games\Silver Pines: drag the game folder onto this file, or set SILVER_PINES.
rem All logic stays ASCII: cmd mis-reads batch files after "chcp 65001" when variables (e.g. a path with
rem Chinese characters) expand to multi-byte text, so the code page is switched only to print the messages.
set "GAME=D:\Games\Silver Pines"
if defined SILVER_PINES set "GAME=%SILVER_PINES%"
if not "%~1"=="" set "GAME=%~1"
set "AA=%GAME%\Carpenter_Data\StreamingAssets\aa"
set "SW=%AA%\StandaloneWindows64"
set "GGM=%GAME%\Carpenter_Data\globalgamemanagers"
set "BUNDLE=team17_auto_base_characters_compressed_assets_player.bundle"
set "HERE=%~dp0"
set "LIST=%HERE%build\patches\bundles.txt"
set "MSG=fail"
set "N=0"
set "SKIPPED="

if not exist "%SW%\%BUNDLE%" (set "MSG=no_game" & goto :show)
tasklist /FI "IMAGENAME eq Carpenter.exe" | "%SystemRoot%\System32\find.exe" /I "Carpenter.exe" >nul
if not errorlevel 1 (set "MSG=running" & goto :show)
if not exist "%HERE%build\%BUNDLE%" (set "MSG=no_build" & goto :show)
if not exist "%LIST%" (set "MSG=no_build" & goto :show)

if not exist "%HERE%backup\patches" mkdir "%HERE%backup\patches"
call :backup "%SW%\%BUNDLE%" "%HERE%backup\%BUNDLE%" "%HERE%build\%BUNDLE%" || goto :show
if not exist "%HERE%backup\catalog.bin" (
  copy /Y "%AA%\catalog.bin" "%HERE%backup\catalog.bin" >nul || goto :show
)
if exist "%HERE%build\globalgamemanagers" (
  call :backup "%GGM%" "%HERE%backup\globalgamemanagers" "%HERE%build\globalgamemanagers" || goto :show
)
for /f "usebackq delims=" %%F in ("%LIST%") do (
  call :backup "%SW%\%%F" "%HERE%backup\patches\%%F" "%HERE%build\patches\%%F" || goto :show
)

copy /Y "%HERE%build\%BUNDLE%" "%SW%\%BUNDLE%" >nul || goto :show
for /f "usebackq delims=" %%F in ("%LIST%") do (
  copy /Y "%HERE%build\patches\%%F" "%SW%\%%F" >nul || goto :show
  set /a N+=1
)

rem the audio switch only goes in when globalgamemanagers matches the game version it was made from
set "MSG=done"
if not exist "%HERE%build\globalgamemanagers" goto :installed
set "MSG=done_no_sound"
for %%A in ("%GGM%") do set "SZ_GAME=%%~zA"
for %%A in ("%HERE%build\globalgamemanagers") do set "SZ_MOD=%%~zA"
if not "%SZ_GAME%"=="%SZ_MOD%" goto :installed
copy /Y "%HERE%build\globalgamemanagers" "%GGM%" >nul || (set "MSG=fail" & goto :show)
set "MSG=done"

:installed
if defined SKIPPED set "MSG=%MSG%_upgrade"
goto :show

:backup
rem %1 game file, %2 its backup, %3 the mod's copy. Backs the game file up once. A game file that already
rem equals the mod's copy (an earlier version of the mod is installed and this folder has no backup of it) is no
rem original: it is listed in backup\no_original.txt instead, for the uninstaller's message.
if exist "%~2" exit /b 0
if not "%~z1"=="%~z3" goto :backup_copy
"%SystemRoot%\System32\fc.exe" /b "%~1" "%~3" >nul 2>&1 || goto :backup_copy
>>"%HERE%backup\no_original.txt" echo %~nx1
set "SKIPPED=1"
exit /b 0
:backup_copy
copy /Y "%~1" "%~2" >nul || exit /b 1
exit /b 0

:show
chcp 65001 >nul
goto :msg_%MSG%

:msg_done
echo 安装完成！启动游戏后主角就是奶蛙了。
echo   main bundle + %N% patch bundles
echo 原版文件已备份到这个文件夹里的 backup 文件夹，卸载要用，请不要删除。
pause
exit /b 0

:msg_done_no_sound
echo 安装完成！启动游戏后主角就是奶蛙了。
echo   main bundle + %N% patch bundles
echo 注意：游戏版本和 mod 对不上，待机大笑的音效没有打开（动画照常）。
echo 原版文件已备份到这个文件夹里的 backup 文件夹，卸载要用，请不要删除。
pause
exit /b 0

:msg_done_upgrade
echo 安装完成！启动游戏后主角就是奶蛙了。
echo   main bundle + %N% patch bundles
echo 之前装过旧版奶蛙 mod，而且不是从同一个文件夹装的：已经是 mod 版的文件没有原版可以备份。
echo 以后卸载时，除了运行 restore_original.bat，还要在 Steam 里「验证游戏文件的完整性」才能完全恢复原版。
pause
exit /b 0

:msg_done_no_sound_upgrade
echo 安装完成！启动游戏后主角就是奶蛙了。
echo   main bundle + %N% patch bundles
echo 注意：游戏版本和 mod 对不上，待机大笑的音效没有打开（动画照常）。
echo 之前装过旧版奶蛙 mod，而且不是从同一个文件夹装的：已经是 mod 版的文件没有原版可以备份。
echo 以后卸载时，除了运行 restore_original.bat，还要在 Steam 里「验证游戏文件的完整性」才能完全恢复原版。
pause
exit /b 0

:msg_no_game
echo 找不到游戏文件：
echo   %SW%\%BUNDLE%
echo 游戏不在 D:\Games\Silver Pines 的话，把游戏文件夹（里面有 Carpenter.exe）拖到这个 bat 文件上。
pause
exit /b 1

:msg_running
echo 游戏正在运行，请先退出 Silver Pines 再安装。
pause
exit /b 1

:msg_no_build
echo 还没有生成奶蛙资源包（build 文件夹），请先按 README 运行 scripts\frogify.py 和 scripts\frog_extras.py。
pause
exit /b 1

:msg_fail
echo 复制失败（文件被占用或没有权限）。已复制的文件可以用 restore_original.bat 还原。
pause
exit /b 1
