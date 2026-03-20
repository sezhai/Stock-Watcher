@echo off
echo ================================
echo Stock Watcher - Build Obfuscated EXE
echo ================================
echo.

echo [INFO] Step 1: Obfuscating Python code...
if exist dist_obf rmdir /s /q dist_obf
pyarmor gen -O dist_obf "Stock Watcher.py"

echo.
echo [INFO] Step 2: Building EXE file...
echo.

pyinstaller --onefile ^
    --windowed ^
    --name "Stock Watcher" ^
    --icon=app.ico ^
    --add-data "stock_config.json;." ^
    --paths "dist_obf" ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.simpledialog ^
    --hidden-import=tkinter.messagebox ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=requests ^
    --hidden-import=urllib3 ^
    --hidden-import=uuid ^
    --hidden-import=hashlib ^
    --hidden-import=ctypes ^
    --hidden-import=json ^
    --hidden-import=math ^
    --hidden-import=random ^
    --hidden-import=time ^
    --hidden-import=threading ^
    --hidden-import=concurrent.futures ^
    "dist_obf\Stock Watcher.py"

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [OK] Secure EXE build completed!
echo Location: dist\Stock Watcher.exe
echo.
pause