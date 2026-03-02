@echo off
chcp 65001 > nul
echo ================================
echo Stock Monitor - 打包为 EXE
echo ================================
echo.

REM 检查 pyinstaller 是否已安装
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 安装 PyInstaller...
    pip install pyinstaller -q
)

echo 正在构建 EXE 文件...
echo.

pyinstaller --onefile ^
    --windowed ^
    --name "Stock Monitor" ^
    --icon=app.ico ^
    --add-data "stock_config.json;." ^
    --hidden-import=tkinter ^
    --hidden-import=requests ^
    stock_monitor_optimized.py

if errorlevel 1 (
    echo ❌ 构建失败
    pause
    exit /b 1
)

echo.
echo ✓ EXE 构建完成！
echo 文件位置：dist\Stock Monitor.exe
echo.
pause