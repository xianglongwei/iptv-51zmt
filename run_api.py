#!/usr/bin/env python3
"""
启动IPTV API服务的脚本
"""
import os
import sys
import subprocess

# 检查是否安装了Flask
try:
    import flask
    print("Flask已安装，版本:", flask.__version__)
except ImportError:
    print("错误: 未安装Flask，请先安装Flask")
    print("执行命令: pip install flask")
    sys.exit(1)

# 检查是否存在API目录
if not os.path.exists('api'):
    print("错误: 未找到api目录")
    sys.exit(1)

# 检查是否存在app.py文件
if not os.path.exists('api/app.py'):
    print("错误: 未找到api/app.py文件")
    sys.exit(1)

# 启动API服务
print("正在启动IPTV API服务...")
print("服务将运行在 http://localhost:8000")
print("Web界面地址: http://localhost:8000/index.html")
print("按 Ctrl+C 停止服务")
print("\n")

try:
    # 运行Flask应用
    subprocess.run([sys.executable, 'api/app.py'])
except KeyboardInterrupt:
    print("\n服务已停止")
except Exception as e:
    print(f"启动服务时出错: {e}")
    sys.exit(1)