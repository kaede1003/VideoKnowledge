@echo off
setlocal
cd /d "%~dp0"
echo [INFO] Local Ollama origin configuration - NO API key required.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure_ollama_origin.ps1"  %*
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
