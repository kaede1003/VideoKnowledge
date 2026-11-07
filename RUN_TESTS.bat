@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\run_checks.py %*
) else (
    py -3.11 scripts\run_checks.py %*
)
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" echo [ERROR] Checks failed or a required tool is missing. See artifacts\checks.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b %RESULT%
