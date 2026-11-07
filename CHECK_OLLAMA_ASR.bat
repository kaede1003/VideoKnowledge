@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not exist "diagnostics" mkdir "diagnostics"
if not "%~1"=="" (
  "%PYTHON%" scripts\diagnose_ollama_asr.py --wav "%~1" --output "diagnostics\ollama-asr-check.json"
) else (
  "%PYTHON%" scripts\diagnose_ollama_asr.py --output "diagnostics\ollama-asr-check.json"
)
echo.
echo [INFO] See diagnostics\ollama-asr-check.json.
echo [INFO] For HTTP 500, view: %%LOCALAPPDATA%%\Ollama\server.log
pause
endlocal
