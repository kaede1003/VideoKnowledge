@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo [INFO] Stopping the VideoKnowledge local server...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_local_asr.ps1" -ProjectRoot "%~dp0." -Port 8765
if errorlevel 1 goto failure
echo [OK] Stop request completed.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 0

:failure
echo [ERROR] Could not stop the matching process automatically.
echo [HELP] Use Task Manager, or inspect TCP port 8765 in PowerShell.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 1
