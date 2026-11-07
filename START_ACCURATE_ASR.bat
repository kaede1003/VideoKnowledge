@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "VKN_ASR_MODEL_OVERRIDE=small"
echo [INFO] Starting the small multilingual model. First use may download it.
call "%~dp0START_LOCAL_ASR.bat"
exit /b %errorlevel%
