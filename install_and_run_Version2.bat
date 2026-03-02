@echo off
chcp 65001 > nul
echo ================================
echo Stock Monitor - 安装依赖并运行
echo ================================
echo.

REM 检查 Python 是否已安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误：未找到 Python
    echo 请先安装 Python 3.8+ 并添加到 PATH
    pause
    exit /b 1
)

echo ✓ Python 已找到
echo.

REM 升级 pip
echo [1/3] 升级 pip...
python -m pip install --upgrade pip -q

REM 安装依赖
echo [2/3] 安装依赖...
pip install -r requirements.txt -q

if errorlevel 1 (
    echo ❌ 依赖安装失败
    pause
    exit /b 1
)

echo ✓ 依赖安装完成
echo.

REM 运行程序
echo [3/3] 启动应用...
python stock_monitor_optimized.py

pause