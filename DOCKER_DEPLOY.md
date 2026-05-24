# Docker deployment

The image contains application code. Runtime data must be mounted separately at
`/app/data`; otherwise deleting and recreating the container resets the app to
the data packaged in the image.

Persistent files stored in `/app/data`:

- `iptv_manager.db`
- `2.m3u`
- `crawler_config.json`
- `published_config.json`

## Run from Docker Hub

```bash
mkdir -p /volume1/docker/iptv/data

docker pull lean16/iptv-iptv:latest

docker run -d --name iptv \
  -p 8099:8000 \
  -v /volume1/docker/iptv/data:/app/data \
  --restart unless-stopped \
  lean16/iptv-iptv:latest
```

Use the NAS path that matches your device. The important part is that the host
folder is mounted to `/app/data` in the container with read/write access.

## Update the image without losing data

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

Do not delete `/volume1/docker/iptv/data`.

## Migrate data from an old container

If the old container was not using a volume, copy the files out before deleting
it:

```bash
mkdir -p /volume1/docker/iptv/data
docker cp iptv:/app/iptv_manager.db /volume1/docker/iptv/data/iptv_manager.db
docker cp iptv:/app/2.m3u /volume1/docker/iptv/data/2.m3u
docker cp iptv:/app/crawler_config.json /volume1/docker/iptv/data/crawler_config.json
docker cp iptv:/app/published_config.json /volume1/docker/iptv/data/published_config.json
```

If the old container already used `/app/data`, copy that directory instead:

```bash
docker cp iptv:/app/data/. /volume1/docker/iptv/data/
```

Then recreate the container with `-v /volume1/docker/iptv/data:/app/data`.

## Verify the mount

```bash
docker exec iptv sh -lc 'mount | grep /app/data && ls -l /app/data'
docker exec iptv sh -lc 'python - <<PY
from backend.database import DB_PATH
from backend.m3u_file_editor import M3U_FILE
from backend.crawler_config import load_crawler_config
print(DB_PATH)
print(M3U_FILE)
print(load_crawler_config()["resolved_m3u_file"])
PY'
```

The printed paths should all start with `/app/data/`.
