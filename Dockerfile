# 使用Python 3.11作为基础镜像
FROM python:3.11-slim

# 安装系统依赖（lxml编译 + ffmpeg预览）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt1-dev \
    gcc \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制requirements.txt文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 暴露端口（服务实际运行在8000端口）
EXPOSE 8000

# 运行命令
CMD ["python", "run.py"]
