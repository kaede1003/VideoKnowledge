@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "%~dp0extension\manifest.json" goto extension_missing
start "" msedge "edge://extensions/"
explorer "%~dp0extension"
echo [INFO] Enable Developer mode in Edge.
echo [INFO] Select Load unpacked and choose the extension folder.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 0
:extension_missing
echo [ERROR] Extension files are missing. Re-extract the full ZIP package.
if /i not "%VKN_NO_PAUSE%"=="1" pause
exit /b 1
