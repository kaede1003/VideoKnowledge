@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [ERROR] Project Python environment is missing. Run INSTALL_ALL.bat -Profile speaker.
    pause
    exit /b 1
)
"%PYEXE%" -c "import json; from server.speaker import availability; state=availability(); print(json.dumps(state, ensure_ascii=False, indent=2)); raise SystemExit(0 if state['available'] else 1)"
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" echo [HELP] Stop the service, run INSTALL_SPEAKER_MODEL.bat, then restart.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b %RESULT%
