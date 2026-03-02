#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Monitor - 快速启动脚本
自动检查并安装依赖
"""

import subprocess
import sys
import os

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
    
    # 运行程序
    os.system(f"{sys.executable} stock_monitor_optimized.py")