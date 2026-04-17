#!/usr/bin/env python3
"""
检查Flask是否安装成功的脚本
"""
import sys

print("Python版本:", sys.version)
print("Python路径:", sys.executable)
print("\n尝试导入Flask...")

try:
    import flask
    print("Flask导入成功!")
    print("Flask版本:", flask.__version__)
except ImportError as e:
    print("Flask导入失败:", e)
    print("\n检查Python路径:")
    for path in sys.path:
        print(path)
