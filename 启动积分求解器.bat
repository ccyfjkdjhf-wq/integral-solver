@echo off
setlocal
cd /d "%~dp0"
title Integral Solver

where python >nul 2>nul
if errorlevel 1 goto :no_python

python "%~dp0launcher.py"
if errorlevel 1 pause
exit /b 0

:no_python
echo.
echo  [ERROR] Python 3.10+ was not found.
echo  Please install Python from https://www.python.org/downloads/
echo  and tick "Add Python to PATH", then run this file again.
echo.
pause
exit /b 1
