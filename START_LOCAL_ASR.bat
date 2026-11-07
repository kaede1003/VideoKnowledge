@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

REM Load ASR preferences without modifying existing user settings.
if exist "%~dp0ASR_SETTINGS.bat" call "%~dp0ASR_SETTINGS.bat"
if defined VKN_ASR_MODEL_OVERRIDE set "VKN_ASR_MODEL=%VKN_ASR_MODEL_OVERRIDE%"
if not defined VKN_ASR_MODEL set "VKN_ASR_MODEL=small"
if not defined VKN_ASR_DEVICE set "VKN_ASR_DEVICE=cpu"
if not defined VKN_ASR_COMPUTE set "VKN_ASR_COMPUTE=int8"
if not defined VKN_ASR_LANGUAGE set "VKN_ASR_LANGUAGE=auto"
REM Recognition cadence is configured in extension settings (default 12 seconds).

set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    call :create_venv
    if errorlevel 1 goto python_error
)

REM v050 forces existing installations to receive WebSocket support.
if not exist ".venv\.vkn_deps_v050.ok" (
    call :install_deps
    if errorlevel 1 goto install_error
)

REM Check the actual module needed for HTTP-to-WebSocket upgrades.
"%PYEXE%" -c "import fastapi, uvicorn, faster_whisper, numpy, httpx, PIL, websockets" >nul 2>&1
if errorlevel 1 (
    echo [WARN] A required module is missing. Repairing dependencies.
    call :install_deps
    if errorlevel 1 goto install_error
)
"%PYEXE%" -c "import fastapi, uvicorn, faster_whisper, numpy, httpx, PIL, websockets" >nul 2>&1
if errorlevel 1 goto ws_error

REM A previous copy of the local service must not occupy the same port.
"%PYEXE%" -c "import socket,sys;s=socket.socket();s.settimeout(0.6);taken=s.connect_ex(('127.0.0.1',8765))==0;s.close();sys.exit(1 if taken else 0)"
if errorlevel 1 goto port_busy

echo.
echo [INFO] VideoKnowledge ASR and LoRA local service v0.11.0
echo [INFO] Health URL: http://127.0.0.1:8765/health
"%PYEXE%" "scripts\show_asr_profile.py"
if errorlevel 1 goto failure
echo [INFO] First transcription may download the selected model.
echo [INFO] Stop: press Ctrl+C or run STOP_LOCAL_ASR.bat.
echo.
if exist ".venv\.vkn_stop_requested" del /q ".venv\.vkn_stop_requested" >nul 2>&1
REM Runner records bounded logs and fault traces.
"%PYEXE%" -u "scripts\run_local_service.py"
set "SERVER_EXIT=%errorlevel%"
if exist ".venv\.vkn_stop_requested" (
    del /q ".venv\.vkn_stop_requested" >nul 2>&1
    echo [OK] Local ASR server stopped by user.
    exit /b 0
)
if not "%SERVER_EXIT%"=="0" goto server_error
exit /b 0

:create_venv
echo [INFO] Creating a local Python environment.
py -3.11 -m venv ".venv" >nul 2>&1
if not errorlevel 1 exit /b 0
py -3.12 -m venv ".venv" >nul 2>&1
if not errorlevel 1 exit /b 0
python -m venv ".venv" >nul 2>&1
if not errorlevel 1 exit /b 0
exit /b 1

:install_deps
echo [INFO] Installing or repairing packages; includes WebSocket transport.
"%PYEXE%" -m pip --version >nul 2>&1
if errorlevel 1 exit /b 1
"%PYEXE%" -m pip install -r "server\requirements.txt"
if errorlevel 1 exit /b 1
> ".venv\.vkn_deps_v050.ok" echo v050
exit /b 0

:port_busy
echo.
echo [ERROR] TCP port 8765 is occupied. An old service may still be running.
echo [HELP] Run STOP_LOCAL_ASR.bat, then start again.
echo [HELP] Do not run two copies of the local service at the same time.
goto failure

:ws_error
echo.
echo [ERROR] WebSocket transport is unavailable after repair.
echo [HELP] Run: .venv\Scripts\python.exe -m pip install "websockets>=13,<17"
goto failure

:python_error
echo [ERROR] Python 3.11 or 3.12 not found, or virtual environment creation failed.
echo [HELP] Install 64-bit Python 3.11 and try again.
goto failure

:install_error
echo [ERROR] Python dependency installation failed.
echo [HELP] Check internet access and review the pip error shown above.
goto failure

:server_error
echo [ERROR] Local service exited unexpectedly. Read diagnostics\local-service-state.json and the log.
echo [HELP] Run CHECK_LOCAL_SERVICE.bat. Do not delete your cached audio or notes.
goto failure

:failure
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 1
