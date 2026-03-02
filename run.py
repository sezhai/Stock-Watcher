#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Watcher - 快速启动脚本
自动检查并安装依赖
"""

import subprocess
import sys

def check_and_install_requirements():
    """检查并安装依赖"""
    try:
        import requests
        from requests.adapters import HTTPAdapter
    except ImportError:
        print("检测到缺少依赖，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

if __name__ == "__main__":
    # 检查依赖
    check_and_install_requirements()
    
    # 修复：使用 subprocess.run 替代 os.system，彻底避免空格解析错误
    try:
        subprocess.run([sys.executable, "Stock Watcher.py"], check=True)
    except Exception as e:
        print(f"程序运行出错: {e}")
        input("按回车键退出...") # 防止报错时窗口瞬间关闭