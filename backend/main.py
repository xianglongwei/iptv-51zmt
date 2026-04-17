"""
Lumina-IPTV Backend
FastAPI REST API
"""
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import asc, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from backend.crawler_config import load_crawler_config, save_crawler_config
from backend.crawler import ChannelCrawler
from backend.database import AsyncSessionLocal, ChannelPool, SelectedChannel, get_db, init_db
from backend.m3u_generator import M3uGenerator
from backend.preview_manager import PreviewManager
from backend.published_config import load_published_config, save_published_config
from backend.validator import ChannelValidator


class SelectedCreateRequest(BaseModel):
    pool_id: int
    custom_name: Optional[str] = None
    catchup_enabled: bool = False


class SelectedBatchRequest(BaseModel):
    pool_ids: list[int] = Field(default_factory=list)


class SelectedReorderRequest(BaseModel):
    id: int
    order: int


class PreviewSessionRequest(BaseModel):
    url: str


class CrawlerConfigRequest(BaseModel):
    api_url: str
    m3u_file: str
    rtp_prefix: str
    playseek_param: str
    interval_hours: int = Field(default=12, ge=1, le=168)
    source_tag: str = "爬虫默认源"


class PublishedConfigRequest(BaseModel):
    playlist_filename: str = Field(default="my_list.m3u")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print("[OK] Database initialized")

    from backend.scheduler import start_scheduler, stop_scheduler

    await start_scheduler()
    print("[OK] Scheduler started")
    try:
        yield
    finally:
        await preview_manager.shutdown()
        await stop_scheduler()
        print("[OK] Scheduler stopped")


app = FastAPI(
    title="Lumina-IPTV API",
    description="IPTV Channel Management System",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

preview_manager = PreviewManager(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "preview_cache")
)


def frontend_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "frontend",
        "index.html",
    )


async def get_next_sort_order(db: AsyncSession) -> int:
    result = await db.execute(select(func.max(SelectedChannel.sort_order)))
    return (result.scalar() or 0) + 1


def infer_file_source_tag(filename: str | None, fallback: str = "手动文件导入") -> str:
    cleaned = (filename or "").strip()
    if not cleaned:
        return fallback
    return f"文件: {os.path.basename(cleaned)}"


def infer_url_source_tag(url: str, fallback: str = "手动链接导入") -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return fallback
    path = parsed.path.strip("/")
    if path:
        suffix = path if len(path) <= 32 else f"...{path[-29:]}"
        return f"链接: {parsed.netloc}/{suffix}"
    return f"链接: {parsed.netloc}"


def get_source_kind(source_tag: str | None) -> str:
    value = repair_mojibake((source_tag or "").strip())
    if value.startswith("鏂囦欢:") or value.startswith("æä»¶:"):
        return "file"
    if value.startswith("閾炬帴:") or value.startswith("é¾æ¥:"):
        return "url"
    if "鐖櫕" in value or "ç¬è«" in value:
        return "crawler"
    return "manual"


def get_source_display_name(source_tag: str | None) -> str:
    value = repair_mojibake((source_tag or "").strip())
    if not value:
        return "鏈懡鍚嶆潵婧?"
    if value.startswith("鏂囦欢:") or value.startswith("閾炬帴:"):
        return value.split(":", 1)[1].strip() or value
    return value


def repair_mojibake(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if repaired else text


def get_source_kind(source_tag: str | None) -> str:
    value = repair_mojibake((source_tag or "").strip())
    if value.startswith("\u6587\u4ef6:"):
        return "file"
    if value.startswith("\u94fe\u63a5:"):
        return "url"
    if "\u722c\u866b" in value:
        return "crawler"
    return "manual"


def get_source_display_name(source_tag: str | None) -> str:
    value = repair_mojibake((source_tag or "").strip())
    if not value:
        return "\u672a\u547d\u540d\u6765\u6e90"
    if value.startswith("\u6587\u4ef6:") or value.startswith("\u94fe\u63a5:"):
        return value.split(":", 1)[1].strip() or value
    return value


def serialize_source(name: str, count: int) -> dict:
    kind = get_source_kind(name)
    can_delete = kind in {"file", "url", "manual"}
    return {
        "name": name,
        "count": count,
        "kind": kind,
        "display_name": get_source_display_name(name),
        "is_manual_import": can_delete,
        "can_delete": can_delete,
    }


def apply_channel_sorting(stmt, sort_by: str, sort_direction: str):
    direction = desc if sort_direction == "desc" else asc
    nulls_last = case((ChannelPool.latency_ms.is_(None), 1), else_=0)

    if sort_by == "name":
        return stmt.order_by(direction(ChannelPool.tvg_name), asc(ChannelPool.group_title), asc(ChannelPool.id))
    if sort_by == "latency":
        return stmt.order_by(asc(nulls_last), direction(ChannelPool.latency_ms), asc(ChannelPool.tvg_name))
    if sort_by == "last_check":
        return stmt.order_by(asc(case((ChannelPool.last_check.is_(None), 1), else_=0)), direction(ChannelPool.last_check), asc(ChannelPool.tvg_name))
    if sort_by == "source":
        return stmt.order_by(direction(ChannelPool.source_tag), asc(ChannelPool.group_title), asc(ChannelPool.tvg_name))
    if sort_by == "updated":
        return stmt.order_by(direction(ChannelPool.updated_at), asc(ChannelPool.tvg_name))
    if sort_by == "status":
        return stmt.order_by(direction(ChannelPool.is_active), asc(nulls_last), asc(ChannelPool.latency_ms), asc(ChannelPool.tvg_name))
    return stmt.order_by(direction(ChannelPool.group_title), asc(ChannelPool.tvg_name), asc(ChannelPool.id))


@app.get("/")
async def root():
    return FileResponse(frontend_path())


@app.get("/api")
async def api_info():
    return {"name": "Lumina-IPTV API", "version": "1.1.0", "docs": "/docs"}


@app.get("/api/channels")
async def get_channels(
    group: Optional[str] = None,
    source_tag: Optional[str] = None,
    active_only: bool = False,
    sort_by: str = Query("group"),
    sort_direction: str = Query("asc"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ChannelPool)
    if group:
        stmt = stmt.where(ChannelPool.group_title == group)
    if source_tag:
        stmt = stmt.where(ChannelPool.source_tag == source_tag)
    if active_only:
        stmt = stmt.where(ChannelPool.is_active.is_(True))

    stmt = apply_channel_sorting(stmt, sort_by=sort_by, sort_direction=sort_direction)
    result = await db.execute(stmt)
    channels = result.scalars().all()
    return {"total": len(channels), "channels": [channel.to_dict() for channel in channels]}


@app.get("/api/channels/{channel_id}")
async def get_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChannelPool).where(ChannelPool.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel.to_dict()


@app.put("/api/channels/{channel_id}")
async def update_channel(
    channel_id: int,
    tvg_name: Optional[str] = None,
    group_title: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ChannelPool).where(ChannelPool.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if tvg_name is not None:
        channel.tvg_name = tvg_name
    if group_title is not None:
        channel.group_title = group_title
    channel.updated_at = datetime.now()

    await db.commit()
    return channel.to_dict()


@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChannelPool).where(ChannelPool.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    await db.delete(channel)
    await db.commit()
    return {"status": "deleted", "id": channel_id}


@app.get("/api/groups")
async def get_groups(source_tag: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ChannelPool.group_title, func.count(ChannelPool.id).label("count"))
        .where(ChannelPool.group_title.is_not(None))
    )
    if source_tag:
        stmt = stmt.where(ChannelPool.source_tag == source_tag)

    group_rows = await db.execute(
        stmt.group_by(ChannelPool.group_title).order_by(ChannelPool.group_title)
    )
    total = (await db.execute(select(func.count(ChannelPool.id)))).scalar() or 0
    active = (
        await db.execute(select(func.count(ChannelPool.id)).where(ChannelPool.is_active.is_(True)))
    ).scalar() or 0
    selected = (await db.execute(select(func.count(SelectedChannel.id)))).scalar() or 0

    return {
        "groups": [{"name": name, "count": count} for name, count in group_rows.all() if name],
        "stats": {
            "total": total,
            "active": active,
            "inactive": total - active,
            "selected": selected,
        },
    }


@app.get("/api/sources")
async def get_sources(group: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ChannelPool.source_tag, func.count(ChannelPool.id).label("count"))
        .where(ChannelPool.source_tag.is_not(None))
    )
    if group:
        stmt = stmt.where(ChannelPool.group_title == group)

    result = await db.execute(stmt.group_by(ChannelPool.source_tag).order_by(ChannelPool.source_tag))
    return {
        "sources": [serialize_source(name, count) for name, count in result.all() if name],
        "selected_group": group,
    }


@app.delete("/api/sources")
async def delete_source(
    source_tag: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    normalized = source_tag.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="source_tag is required")
    if get_source_kind(normalized) == "crawler":
        raise HTTPException(status_code=400, detail="Default crawler source cannot be deleted")

    source_rows = await db.execute(
        select(ChannelPool.id).where(ChannelPool.source_tag == normalized)
    )
    pool_ids = [row[0] for row in source_rows.all()]
    if not pool_ids:
        raise HTTPException(status_code=404, detail="Source not found")

    selected_rows = await db.execute(
        select(SelectedChannel).where(SelectedChannel.pool_id.in_(pool_ids))
    )
    selected_items = selected_rows.scalars().all()
    selected_count = len(selected_items)
    for item in selected_items:
        await db.delete(item)

    channel_rows = await db.execute(
        select(ChannelPool).where(ChannelPool.source_tag == normalized)
    )
    channels = channel_rows.scalars().all()
    deleted_count = len(channels)
    for channel in channels:
        await db.delete(channel)

    await db.commit()
    return {
        "status": "deleted",
        "source_tag": normalized,
        "deleted_channels": deleted_count,
        "deleted_selected": selected_count,
    }


@app.get("/api/crawler/config")
async def get_crawler_config():
    return load_crawler_config()


@app.put("/api/crawler/config")
async def update_crawler_config(request: CrawlerConfigRequest):
    from backend.scheduler import get_scheduler_state as scheduler_state
    from backend.scheduler import reload_crawler_schedule

    try:
        payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
        config = save_crawler_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await reload_crawler_schedule()
    return {
        "status": "success",
        "config": config,
        "scheduler": scheduler_state(),
    }


@app.post("/api/import/file")
async def import_from_file(
    file: UploadFile = File(...),
    source_tag: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith((".m3u", ".m3u8")):
        raise HTTPException(status_code=400, detail="Only .m3u files allowed")

    import tempfile

    with tempfile.NamedTemporaryFile(delete=False, suffix=".m3u") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        crawler = ChannelCrawler(db)
        effective_source_tag = source_tag.strip() or infer_file_source_tag(file.filename)
        result = await crawler.import_from_m3u_file(tmp_path, effective_source_tag)
        return {"status": "success", "result": result, "source_tag": effective_source_tag}
    finally:
        os.unlink(tmp_path)


@app.post("/api/import/url")
async def import_from_url(
    url: str = Query(...),
    source_tag: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    crawler = ChannelCrawler(db)
    effective_source_tag = source_tag.strip() or infer_url_source_tag(url)
    result = await crawler.import_from_m3u_url(url, effective_source_tag)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "success", "result": result, "source_tag": effective_source_tag}


@app.post("/api/validate/all")
async def validate_all_channels(db: AsyncSession = Depends(get_db)):
    validator = ChannelValidator(db)
    return await validator.check_all_channels()


@app.post("/api/validate/{channel_id}")
async def validate_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    validator = ChannelValidator(db)
    result = await validator.check_channel_by_id(channel_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/preview/stream")
async def preview_stream(url: str = Query(..., description="HTTP stream URL to proxy")):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Only HTTP/HTTPS streams can be previewed in browser")

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0),
        follow_redirects=True,
        headers={
            "User-Agent": "Lumina-IPTV Preview/1.0",
            "Accept": "*/*",
        },
    )

    try:
        request = client.build_request("GET", url)
        upstream = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Unable to open preview stream: {exc}") from exc

    if upstream.status_code >= 400:
        error_body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        detail = error_body.decode("utf-8", errors="ignore")[:200] or f"Upstream responded with {upstream.status_code}"
        raise HTTPException(status_code=upstream.status_code, detail=detail)

    async def iterator():
        async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
            if chunk:
                yield chunk

    async def cleanup():
        await upstream.aclose()
        await client.aclose()

    passthrough_headers = {}
    for header_name in ("content-type", "cache-control", "accept-ranges"):
        if header_name in upstream.headers:
            passthrough_headers[header_name] = upstream.headers[header_name]

    return StreamingResponse(
        iterator(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers=passthrough_headers,
        background=BackgroundTask(cleanup),
    )


@app.post("/api/preview/session")
async def create_preview_session(request: PreviewSessionRequest):
    parsed = urlparse(request.url)
    if parsed.scheme not in {"http", "https", "rtp", "rtsp", "udp"}:
        raise HTTPException(status_code=400, detail="Unsupported preview protocol")

    try:
        session = await preview_manager.start_session(request.url)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "session_id": session.session_id,
        "playlist_url": f"/api/preview/hls/{session.session_id}/index.m3u8",
    }


@app.delete("/api/preview/session/{session_id}")
async def remove_preview_session(session_id: str):
    await preview_manager.stop_session(session_id)
    return {"status": "stopped"}


@app.get("/api/preview/hls/{session_id}/{filename:path}")
async def preview_hls_file(session_id: str, filename: str):
    session = preview_manager.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Preview session not found")

    safe_filename = os.path.normpath(filename).replace("\\", "/")
    if safe_filename.startswith("../") or safe_filename == "..":
        raise HTTPException(status_code=400, detail="Invalid preview file")

    file_path = os.path.join(session.directory, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Preview segment not found")

    media_type = "application/vnd.apple.mpegurl" if file_path.endswith(".m3u8") else "video/mp2t"
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/api/selected")
async def get_selected_channels(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SelectedChannel, ChannelPool)
        .join(ChannelPool, SelectedChannel.pool_id == ChannelPool.id)
        .order_by(SelectedChannel.sort_order, SelectedChannel.id)
    )

    channels = []
    for selected, pool in result.all():
        data = pool.to_dict()
        data["selected_id"] = selected.id
        data["pool_id"] = selected.pool_id
        data["custom_name"] = selected.custom_name
        data["sort_order"] = selected.sort_order
        data["catchup_enabled"] = selected.catchup_enabled
        channels.append(data)

    return {"total": len(channels), "channels": channels}


@app.post("/api/selected")
async def add_selected_channel(
    request: SelectedCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    if not request.pool_id:
        raise HTTPException(status_code=400, detail="pool_id is required")

    existing = await db.execute(
        select(SelectedChannel).where(SelectedChannel.pool_id == request.pool_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Channel already selected")

    selected = SelectedChannel(
        pool_id=request.pool_id,
        custom_name=request.custom_name,
        catchup_enabled=request.catchup_enabled,
        sort_order=await get_next_sort_order(db),
    )
    db.add(selected)
    await db.commit()
    return {"status": "added", "id": selected.id}


@app.post("/api/selected/batch")
async def add_selected_batch(
    request: SelectedBatchRequest,
    db: AsyncSession = Depends(get_db),
):
    pool_ids = []
    seen = set()
    for pool_id in request.pool_ids:
        if pool_id not in seen:
            pool_ids.append(pool_id)
            seen.add(pool_id)

    if not pool_ids:
        raise HTTPException(status_code=400, detail="pool_ids is required")

    added = 0
    next_order = await get_next_sort_order(db)
    for pool_id in pool_ids:
        existing = await db.execute(select(SelectedChannel).where(SelectedChannel.pool_id == pool_id))
        if existing.scalar_one_or_none():
            continue
        db.add(SelectedChannel(pool_id=pool_id, sort_order=next_order))
        next_order += 1
        added += 1

    await db.commit()
    return {"status": "added", "count": added}


@app.delete("/api/selected/{selected_id}")
async def remove_selected_channel(selected_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SelectedChannel).where(SelectedChannel.id == selected_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Selected channel not found")

    await db.delete(channel)
    await db.commit()
    return {"status": "deleted"}


@app.delete("/api/selected")
async def clear_selected_channels(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SelectedChannel))
    for channel in result.scalars().all():
        await db.delete(channel)
    await db.commit()
    return {"status": "cleared"}


@app.put("/api/selected/{selected_id}")
async def update_selected_channel(
    selected_id: int,
    custom_name: Optional[str] = None,
    sort_order: Optional[int] = None,
    catchup_enabled: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SelectedChannel).where(SelectedChannel.id == selected_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Selected channel not found")

    if custom_name is not None:
        channel.custom_name = custom_name
    if sort_order is not None:
        channel.sort_order = sort_order
    if catchup_enabled is not None:
        channel.catchup_enabled = catchup_enabled

    await db.commit()
    return channel.to_dict()


@app.post("/api/selected/reorder")
async def reorder_selected_channels(
    orders: list[SelectedReorderRequest],
    db: AsyncSession = Depends(get_db),
):
    for item in orders:
        result = await db.execute(select(SelectedChannel).where(SelectedChannel.id == item.id))
        channel = result.scalar_one_or_none()
        if channel:
            channel.sort_order = item.order
    await db.commit()
    return {"status": "reordered"}


@app.get("/api/published/config")
async def get_published_config():
    return load_published_config()


@app.put("/api/published/config")
async def update_published_config(request: PublishedConfigRequest):
    try:
        payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
        return save_published_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/my_list.m3u")
async def get_my_list(
    use_catchup: bool = Query(True),
    rtp_prefix: str = Query("http://192.168.10.1:10000/rtp/"),
):
    async with AsyncSessionLocal() as db:
        generator = M3uGenerator(db)
        content = await generator.generate_selected_m3u(
            use_catchup=use_catchup,
            rtp_prefix=rtp_prefix,
        )
    return PlainTextResponse(content, media_type="audio/x-mpegurl")


@app.get("/playlist/{playlist_name}")
async def get_named_my_list(
    playlist_name: str,
    use_catchup: bool = Query(True),
    rtp_prefix: str = Query("http://192.168.10.1:10000/rtp/"),
):
    config = load_published_config()
    if playlist_name != config["playlist_filename"]:
        raise HTTPException(status_code=404, detail="Playlist not found")
    async with AsyncSessionLocal() as db:
        generator = M3uGenerator(db)
        content = await generator.generate_selected_m3u(
            use_catchup=use_catchup,
            rtp_prefix=rtp_prefix,
        )
    return PlainTextResponse(
        content,
        media_type="audio/x-mpegurl",
        headers={"Content-Disposition": f'inline; filename="{playlist_name}"'},
    )


@app.get("/all.m3u")
async def get_all_m3u(
    active_only: bool = Query(True),
    use_catchup: bool = Query(False),
    rtp_prefix: str = Query("http://192.168.10.1:10000/rtp/"),
):
    async with AsyncSessionLocal() as db:
        generator = M3uGenerator(db)
        content = await generator.generate_all_active_m3u(
            use_catchup=use_catchup,
            rtp_prefix=rtp_prefix,
        )
    return PlainTextResponse(content, media_type="audio/x-mpegurl")


@app.get("/group/{group}.m3u")
async def get_group_m3u(
    group: str,
    use_catchup: bool = Query(False),
    rtp_prefix: str = Query("http://192.168.10.1:10000/rtp/"),
):
    async with AsyncSessionLocal() as db:
        generator = M3uGenerator(db)
        content = await generator.generate_group_m3u(
            group_title=group,
            use_catchup=use_catchup,
            rtp_prefix=rtp_prefix,
        )
    return PlainTextResponse(content, media_type="audio/x-mpegurl")


@app.get("/api/scheduler")
async def get_scheduler_state():
    from backend.scheduler import get_scheduler_state as scheduler_state

    return scheduler_state()



@app.post("/api/crawler/run")
async def run_crawler():
    """Manually trigger the crawler script and return runtime state."""
    from backend.scheduler import run_crawler_pipeline

    try:
        return await run_crawler_pipeline(trigger="manual")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Crawler timeout after 120 seconds")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(ChannelPool.id)))).scalar() or 0
    active = (
        await db.execute(select(func.count(ChannelPool.id)).where(ChannelPool.is_active.is_(True)))
    ).scalar() or 0
    selected = (await db.execute(select(func.count(SelectedChannel.id)))).scalar() or 0

    return {
        "channel_pool": {"total": total, "active": active, "inactive": total - active},
        "selected_channels": selected,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
