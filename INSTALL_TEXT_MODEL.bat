@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
echo [INFO] Legacy shortcut. For all components use INSTALL_ALL.bat.
call "%~dp0INSTALL_ALL.bat" -Profile text %*
exit /b %errorlevel%
