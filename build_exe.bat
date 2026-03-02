@echo off
echo ================================
echo Stock Watcher - Build EXE
echo ================================
echo.

pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller -q
)

echo [INFO] Building EXE file...
echo.

pyinstaller --onefile ^
    --windowed ^
    --name "Stock Watcher" ^
    --icon=app.ico ^
    --add-data "stock_config.json;." ^
    --hidden-import=tkinter ^
    --hidden-import=requests ^
    "Stock Watcher.py"

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [OK] EXE build completed!
echo Location: dist\Stock Watcher.exe
echo.
pause