@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "VKN_ASR_MODEL_OVERRIDE=small"
echo [INFO] Legacy accuracy mode uses small. An explicit ASR profile takes priority.
call "%~dp0START_LOCAL_ASR.bat"
exit /b %errorlevel%
