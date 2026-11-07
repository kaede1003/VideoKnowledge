@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\check_repo.py %*
) else (
    py -3.11 scripts\check_repo.py %*
)
set "RESULT=%errorlevel%"
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b %RESULT%
