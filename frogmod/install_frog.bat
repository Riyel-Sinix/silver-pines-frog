@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Keep this launcher ASCII. PowerShell handles Unicode paths and messages.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0manage_frog.ps1" -Operation Install -GameDirectory "%~1"
set "FROG_EXIT=%ERRORLEVEL%"
pause
exit /b %FROG_EXIT%
