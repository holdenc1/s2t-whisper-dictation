@echo off
cd /d "%~dp0"

if not exist "venv_cuda\Scripts\pythonw.exe" (
    echo CUDA virtual environment not found.
    pause
    exit /b 1
)

start "" "venv_cuda\Scripts\pythonw.exe" main_gui.py
