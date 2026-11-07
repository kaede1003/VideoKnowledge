@echo off
setlocal
cd /d "%~dp0"
echo Video Knowledge - Local AI timing diagnostic
echo This does NOT update the extension, download models or change settings.
echo Only synthetic test text is sent to your local Ollama.
echo Close other AI tasks before testing. Ctrl+C cancels.
echo.
if exist ".venv\Scripts\python.exe" goto venv
where py >nul 2>nul
if not errorlevel 1 goto launcher
where python >nul 2>nul
if not errorlevel 1 goto python
 echo [ERROR] Python 3.10+ was not found.
 echo Extract these files into your existing VideoKnowledge project folder,
 echo or install Python. No administrator permission is required.
 goto end
:venv
".venv\Scripts\python.exe" "scripts\diagnose_ai_timeout.py" --medium %*
goto end
:launcher
py -3 "scripts\diagnose_ai_timeout.py" --medium %*
goto end
:python
python "scripts\diagnose_ai_timeout.py" --medium %*
:end
echo.
echo Reports, when generated, are in the diagnostics folder.
pause
endlocal
