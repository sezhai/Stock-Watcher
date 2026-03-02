# Stock Watcher（盯盘助手）

## 📋 系统要求

- Windows 7 及以上
- Python 3.8+ （如果从源码运行）

## 功能特点
- 极简悬浮窗：置顶显示，背景半透明，融入桌面。
- 全能监控：A股、港股、美股、黄金、外汇、数字货币全覆盖。
- 智能记忆：自动保存自选股列表及显示模式偏好。
- 便捷配置：内置常用指数与商品预设，一键添加。
- 配置简单：右键菜单设置添加/删除股票。
- 预警提醒：到达设定价格时抖动提醒，点击停止。

## 🚀 使用方法

### 方法 1：直接运行（推荐）

1. **下载文件**
   - 将以下文件放在同一目录：
     - `Stock Watcher.py`
     - `requirements.txt`
     - `install_and_run.bat`

2. **双击运行**
   - 双击 `install_and_run.bat`
   - 脚本会自动：
     - 检查 Python 环境
     - 安装所有依赖
     - 启动应用

### 方法 2：手动运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行程序
python Stock Watcher.py
```

### 方法 3：打包为 EXE（无需 Python）

确保已安装 Python

双击 build_exe.bat

等待构建完成

在 dist 文件夹找到 Stock Watcher.exe

