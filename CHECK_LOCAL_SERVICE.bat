@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [ERROR] Local Python environment missing. Run START_LOCAL_ASR.bat first.
    pause
    exit /b 1
)
"%PYEXE%" "scripts\diagnose_local_service.py"
set "RESULT=%errorlevel%"
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b %RESULT%
