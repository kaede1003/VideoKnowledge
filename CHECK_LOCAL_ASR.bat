@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing_python
if not exist "scripts\check_ws.py" goto missing_check
".venv\Scripts\python.exe" "scripts\check_ws.py"
if errorlevel 1 goto failure
echo [OK] HTTP health check and WebSocket transport check passed.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 0

:missing_python
echo [ERROR] Local Python environment missing. Run START_LOCAL_ASR.bat.
goto failure

:missing_check
echo [ERROR] Diagnostic script missing. Apply the full v0.3.2 patch.
goto failure

:failure
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 1
