@echo off
cd /d "%~dp0"

echo ========================================
echo Setting up Speech-to-Text environment
echo ========================================

echo.
echo Creating virtual environment...
python -m venv venv

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Installing PyTorch with CUDA support...
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

echo.
echo Installing other dependencies...
pip install faster-whisper sounddevice numpy keyboard pyautogui pyperclip pyyaml

echo.
echo ========================================
echo Setup complete!
echo ========================================
echo.
echo To run the application:
echo   1. Double-click run.bat
echo   OR
echo   2. Activate venv: venv\Scripts\activate
echo      Then run: python main.py
echo.
pause
