@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
) else (
    echo Create the virtual environment and install requirements first. See README.md.
    pause
    exit /b 1
)
if errorlevel 1 pause
