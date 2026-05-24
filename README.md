# Lumina IPTV

基于 FastAPI 的 IPTV 管理工具，前端在 `frontend/`，后端在 `backend/`。

## 项目结构

```text
iptv/
├── backend/              # FastAPI API、数据库、爬虫、校验、M3U 生成和文件编辑
├── frontend/             # Web 管理界面
│   ├── index.html        # 主管理后台
│   └── m3u-editor.html   # 直接编辑 2.m3u 的频道编辑器
├── 2.m3u                 # 镜像内默认 M3U 播放列表
├── iptv.py               # 爬虫脚本，由调度器调用
├── run.py                # 本地启动入口
├── requirements.txt      # Python 依赖
├── Dockerfile
├── docker-compose.yml
└── DOCKER_DEPLOY.md      # Docker Hub / NAS 部署说明
```

## 本地启动

```bash
pip install -r requirements.txt
python run.py
```

默认地址：

- 管理后台：`http://localhost:8000`
- 2.m3u 编辑器：`http://localhost:8000/m3u-editor`
- API 文档：`http://localhost:8000/docs`
- 我的播放列表：`http://localhost:8000/my_list.m3u`
- 全部频道：`http://localhost:8000/all.m3u`

## Docker Compose

本地或 NAS 使用 compose 时：

```bash
docker compose up -d --build
```

当前 `docker-compose.yml` 会把宿主机 `./data` 挂载到容器 `/app/data`，端口为：

```text
8099:8000
```

访问：

```text
http://localhost:8099
```

## Docker Hub 部署

构建并推送镜像：

```bash
docker build -t lean16/iptv-iptv:latest .
docker push lean16/iptv-iptv:latest
```

在 NAS 或服务器上运行：

```bash
mkdir -p /volume1/docker/iptv/data

docker pull lean16/iptv-iptv:latest

docker run -d --name iptv \
  -p 8099:8000 \
  -v /volume1/docker/iptv/data:/app/data \
  --restart unless-stopped \
  lean16/iptv-iptv:latest
```

更新镜像时也必须继续挂载同一个数据目录：

```bash
docker pull lean16/iptv-iptv:latest
docker stop iptv
docker rm iptv
docker run -d --name iptv \
  -p 8099:8000 \
  -v /volume1/docker/iptv/data:/app/data \
  --restart unless-stopped \
  lean16/iptv-iptv:latest
```

不要删除 `/volume1/docker/iptv/data`，否则频道、`2.m3u`、配置和数据库会恢复到镜像默认数据。

更多迁移和校验命令见 [DOCKER_DEPLOY.md](DOCKER_DEPLOY.md)。

## 主要功能

- 从文件或 URL 导入 M3U 到频道池
- 选择频道并生成发布播放列表
- 直接在网页端新增、修改、删除 `2.m3u` 里的频道
- 手动或定时运行爬虫，并同步到数据库
- 校验频道可用性和预览频道流
