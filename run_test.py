#!/usr/bin/env python3
"""
Lumina-IPTV 测试启动脚本 (使用端口8001)
"""
import os
import sys
import subprocess

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 确保在正确的目录
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 50)
print("Lumina-IPTV 管理系统 (测试端口8001)")
print("=" * 50)

# 检查依赖
print("\n[1/3] 检查依赖...")
try:
    import fastapi
    import sqlalchemy
    import httpx
    import apscheduler
    print("√ 依赖已安装")
except ImportError as e:
    print(f"× 缺少依赖: {e}")
    print("\n正在安装依赖...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    print("√ 依赖安装完成")

# 检查数据库
print("\n[2/3] 检查数据库...")
db_path = "iptv_manager.db"
if os.path.exists(db_path):
    print(f"√ 数据库已存在: {db_path}")
else:
    print("√ 将创建新数据库")

# 启动服务
print("\n[3/3] 启动服务...")
print("=" * 50)
print("管理后台: http://localhost:8001")
print("API 文档: http://localhost:8001/docs")
print("我的列表: http://localhost:8001/my_list.m3u")
print("全部频道: http://localhost:8001/all.m3u")
print("=" * 50)

# 启动 uvicorn
import uvicorn
from backend.main import app

uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
