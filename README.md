# IPTV 项目

这是一个 IPTV 管理系统，用于管理和播放 IPTV 频道。

## 项目结构

```
iptv/
├── api/             # API 相关代码
├── backend/         # 后端代码
├── frontend/        # 前端代码
├── .github/         # GitHub 工作流配置
├── .vscode/         # VS Code 配置
├── 2.m3u            # M3U 播放列表文件
├── CHANGELOG.md     # 变更日志
├── Channel_Diagnostics.html  # 频道诊断页面
├── FEATURES_UPDATE.md  # 功能更新说明
├── check_flask.py   # Flask 检查脚本
├── crawler_config.json  # 爬虫配置文件
├── index.html       # 主页面
├── iptv.py          # 主脚本
├── iptv_manager.db  # 数据库文件
├── preview_keyframe.ts  # 预览关键帧脚本
├── preview_sample.ts    # 预览示例脚本
├── published_config.json  # 发布配置文件
├── requirements.txt  # 依赖项文件
├── run.py           # 运行脚本
├── run_api.py       # API 运行脚本
├── run_test.py      # 测试运行脚本
├── start_server.ps1  # 启动服务器脚本
├── temp_manual_test.m3u  # 临时手动测试 M3U 文件
├── test.html        # 测试页面
└── updata.html      # 更新页面
```

## 功能特性

- 频道管理：添加、编辑、删除 IPTV 频道
- 播放列表生成：自动生成 M3U 播放列表
- 频道预览：提供频道预览功能
- 爬虫功能：自动抓取 IPTV 源
- API 接口：提供 RESTful API 接口
- 诊断工具：频道诊断功能

## 安装说明

### 1. 克隆项目

```bash
git clone https://github.com/xianglongwei/iptv-51zmt.git
cd iptv-51zmt
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置爬虫

编辑 `crawler_config.json` 文件，配置爬虫参数。

### 4. 启动服务器

使用 PowerShell 运行：

```powershell
.tart_server.ps1
```

或者手动运行：

```bash
python run.py
```

## 使用方法

### 1. 访问主页面

打开浏览器，访问 `http://localhost:5000` 查看主页面。

### 2. 管理频道

通过前端界面添加、编辑、删除频道。

### 3. 生成播放列表

系统会自动生成 M3U 播放列表，可在 `2.m3u` 文件中查看。

### 4. 使用 API

API 接口地址：`http://localhost:5000/api`

## 技术栈

- 前端：HTML、CSS、JavaScript
- 后端：Python、Flask
- 数据库：SQLite
- 爬虫：Python requests、BeautifulSoup

## 开发说明

### 运行测试

```bash
python run_test.py
```

### 运行 API 服务器

```bash
python run_api.py
```

## 贡献

欢迎提交 Issue 和 Pull Request。

## 许可证

MIT
