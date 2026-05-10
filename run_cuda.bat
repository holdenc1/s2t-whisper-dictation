@echo off
cd /d "%~dp0"

if not exist "venv_cuda\Scripts\activate.bat" (
    echo CUDA virtual environment not found.
    pause
    exit /b 1
)

call venv_cuda\Scripts\activate.bat
python main.py
pause
