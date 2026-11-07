@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul
REM Reuse existing ASR choice; never overwrite user preferences.
if exist "%~dp0ASR_SETTINGS.bat" call "%~dp0ASR_SETTINGS.bat"
if not defined VKN_ASR_MODEL set "VKN_ASR_MODEL=small"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_all.ps1" %*
set "INSTALL_EXIT=%errorlevel%"
echo.
if not "%INSTALL_EXIT%"=="0" echo [HELP] Review the failed step. Rerun INSTALL_ALL.bat after fixing it.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b %INSTALL_EXIT%
