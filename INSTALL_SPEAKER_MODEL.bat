@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo [INFO] Updates Sherpa-ONNX to 1.13.8 and verifies speaker models in an isolated process.
call "%~dp0INSTALL_ALL.bat" -Profile speaker %*
exit /b %errorlevel%
