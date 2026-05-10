#!/usr/bin/env python3
"""Start the Lumina IPTV FastAPI application."""
import io
import os
import subprocess
import sys


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("Lumina IPTV 管理系统")
print("=" * 50)

print("\n[1/3] 检查依赖...")
try:
    import apscheduler  # noqa: F401
    import fastapi  # noqa: F401
    import httpx  # noqa: F401
    import sqlalchemy  # noqa: F401

    print("依赖已安装")
except ImportError as exc:
    print(f"缺少依赖: {exc}")
    print("正在安装 requirements.txt ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    print("依赖安装完成")

print("\n[2/3] 检查数据库...")
db_path = "iptv_manager.db"
if os.path.exists(db_path):
    print(f"数据库已存在: {db_path}")
else:
    print("启动后将创建新数据库")

print("\n[3/3] 启动服务...")
print("=" * 50)
print("管理后台: http://localhost:8000")
print("2.m3u 编辑器: http://localhost:8000/m3u-editor")
print("API 文档: http://localhost:8000/docs")
print("我的列表: http://localhost:8000/my_list.m3u")
print("全部频道: http://localhost:8000/all.m3u")
print("=" * 50)

import uvicorn

from backend.main import app


uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
