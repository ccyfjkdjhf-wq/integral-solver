@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
title Integral Solver - CLI

where python >nul 2>nul
if errorlevel 1 goto :no_python

python "%~dp0launcher.py" --cli %*
set "CODE=%ERRORLEVEL%"
echo.
echo  Exit code: %CODE%
pause
exit /b %CODE%

:no_python
echo.
echo  [ERROR] Python 3.10+ was not found.
echo  Please install Python from https://www.python.org/downloads/
echo  and tick "Add Python to PATH", then run this file again.
echo.
pause
exit /b 1
