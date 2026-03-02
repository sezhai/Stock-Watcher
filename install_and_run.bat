@echo off
echo ================================
echo Stock Watcher - Install and Run
echo ================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ and add to PATH.
    pause
    exit /b 1
)
echo [OK] Python found.
echo.

echo [1/3] Upgrading pip...
python -m pip install --upgrade pip -q

echo [2/3] Installing requirements...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)
echo [OK] Requirements installed.
echo.

echo [3/3] Starting application...
python "Stock Watcher.py"

pause