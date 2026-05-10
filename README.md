# Lumina IPTV

一个基于 FastAPI 的 IPTV 管理工具，前端统一放在 `frontend/`，后端统一放在 `backend/`。

## 保留的项目结构

```text
iptv/
├── backend/              # FastAPI API、数据库、爬虫、校验、M3U 生成和文件编辑
├── frontend/             # Web 管理界面
│   ├── index.html        # 主管理后台
│   └── m3u-editor.html   # 直接编辑 2.m3u 的频道编辑器
├── 2.m3u                 # 原始 M3U 播放列表文件
├── iptv.py               # 爬虫脚本，由调度器调用
├── run.py                # 本地启动入口
├── requirements.txt      # Python 依赖
├── crawler_config.json   # 爬虫配置
├── published_config.json # 发布列表配置
├── Dockerfile
└── docker-compose.yml
```

## 启动

```bash
pip install -r requirements.txt
python run.py
```

默认地址：

- 管理后台：`http://localhost:8000`
- 直接编辑 `2.m3u`：`http://localhost:8000/m3u-editor`
- API 文档：`http://localhost:8000/docs`
- 我的播放列表：`http://localhost:8000/my_list.m3u`
- 全部频道：`http://localhost:8000/all.m3u`

## 主要功能

- 从文件或 URL 导入 M3U 到频道池
- 选择频道并生成发布播放列表
- 直接在网页端新增、修改、删除 `2.m3u` 里的频道
- 手动或定时运行爬虫，并同步到数据库
- 校验频道可用性和预览频道流

## Docker

```bash
docker compose up --build
```

当前 `docker-compose.yml` 将宿主机 `5000` 映射到容器 `8000`。
