"""
Background scheduler and crawler runtime state.
"""
import asyncio
import locale
import os
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.crawler_config import load_crawler_config
from backend.crawler import ChannelCrawler
from backend.database import AsyncSessionLocal
from backend.validator import ChannelValidator


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IPTV_SCRIPT = os.path.join(PROJECT_ROOT, "iptv.py")


scheduler = AsyncIOScheduler()


def _serialize_datetime(value):
    return value.isoformat() if value else None


def _begin_job():
    scheduler_state["active_jobs"] += 1
    scheduler_state["is_running"] = scheduler_state["active_jobs"] > 0


def _finish_job():
    scheduler_state["active_jobs"] = max(0, scheduler_state["active_jobs"] - 1)
    scheduler_state["is_running"] = scheduler_state["active_jobs"] > 0


def _decode_output(payload):
    if not payload:
        return ""

    preferred = locale.getpreferredencoding(False) or "utf-8"
    for encoding in ("utf-8", "gbk", preferred):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _tail_lines(text, limit=8):
    return [line.strip() for line in (text or "").splitlines() if line.strip()][-limit:]


def _load_crawler_config():
    return load_crawler_config()


def _get_output_file_state(path, created_default_output=False):
    exists = os.path.exists(path)
    return {
        "path": path,
        "exists": exists,
        "size_bytes": os.path.getsize(path) if exists else 0,
        "last_modified": _serialize_datetime(datetime.fromtimestamp(os.path.getmtime(path))) if exists else None,
        "created_default_output": created_default_output,
    }


def _build_log_tail(stdout_text, stderr_text):
    lines = [f"INFO: {line}" for line in _tail_lines(stdout_text, limit=6)]
    lines.extend(f"ERROR: {line}" for line in _tail_lines(stderr_text, limit=4))
    return lines[-10:]


def _empty_crawler_state():
    config = _load_crawler_config()
    return {
        "status": "idle",
        "running": False,
        "trigger": None,
        "message": "还没有执行过爬虫",
        "last_started_at": None,
        "last_finished_at": None,
        "last_success_at": None,
        "duration_seconds": None,
        "return_code": None,
        "stdout_tail": [],
        "stderr_tail": [],
        "log_tail": [],
        "import_stats": {},
        "created_default_output": False,
        "output_file": _get_output_file_state(config["resolved_m3u_file"]),
        "config": config,
    }


def _finalize_crawler_run(
    *,
    status,
    message,
    started_at,
    finished_at,
    return_code=None,
    stdout_text="",
    stderr_text="",
    import_stats=None,
    trigger=None,
    created_default_output=False,
):
    crawler_state = scheduler_state["crawler"]
    crawler_state.update(
        {
            "status": status,
            "running": False,
            "trigger": trigger,
            "message": message,
            "last_started_at": started_at,
            "last_finished_at": finished_at,
            "duration_seconds": round((finished_at - started_at).total_seconds(), 2) if started_at and finished_at else None,
            "return_code": return_code,
            "stdout_tail": _tail_lines(stdout_text),
            "stderr_tail": _tail_lines(stderr_text),
            "log_tail": _build_log_tail(stdout_text, stderr_text) or [f"{'ERROR' if status == 'error' else 'INFO'}: {message}"],
            "import_stats": import_stats or {},
            "created_default_output": created_default_output,
            "output_file": _get_output_file_state(crawler_state["config"]["resolved_m3u_file"], created_default_output),
        }
    )
    if status == "success":
        crawler_state["last_success_at"] = finished_at


def _refresh_crawler_snapshot():
    crawler_state = scheduler_state["crawler"]
    config = _load_crawler_config()
    crawler_state["config"] = config
    crawler_state["output_file"] = _get_output_file_state(
        config["resolved_m3u_file"],
        crawler_state.get("created_default_output", False),
    )


def _get_job_state(job_id, interval_hours):
    job = scheduler.get_job(job_id)
    return {
        "id": job_id,
        "interval_hours": interval_hours,
        "next_run_time": _serialize_datetime(job.next_run_time) if job and job.next_run_time else None,
    }


scheduler_state = {
    "last_validation": None,
    "last_import": None,
    "is_running": False,
    "active_jobs": 0,
    "validation_stats": {},
    "import_stats": {},
    "crawler": _empty_crawler_state(),
}


async def validate_all_job():
    """Background job to validate all channels."""
    _begin_job()
    print("[...] Starting scheduled validation...")
    try:
        async with AsyncSessionLocal() as db:
            validator = ChannelValidator(db)
            stats = await validator.check_all_channels()
            scheduler_state["validation_stats"] = stats
            scheduler_state["last_validation"] = datetime.now()
            print(f"[OK] Validation complete: {stats['online']}/{stats['total']} online")
    finally:
        _finish_job()


async def run_crawler_pipeline(trigger="manual"):
    """Run iptv.py, import the updated M3U file, and record runtime state."""
    started_at = datetime.now()
    config = _load_crawler_config()
    m3u_file = config["resolved_m3u_file"]
    created_default_output = False
    stdout_text = ""
    stderr_text = ""

    scheduler_state["crawler"].update(
        {
            "status": "running",
            "running": True,
            "trigger": trigger,
            "message": "爬虫已启动，正在执行 iptv.py ...",
            "last_started_at": started_at,
            "last_finished_at": None,
            "duration_seconds": None,
            "return_code": None,
            "stdout_tail": [],
            "stderr_tail": [],
            "log_tail": [f"INFO: 已启动{('定时' if trigger == 'scheduled' else '手动')}爬虫，正在执行 iptv.py"],
            "import_stats": {},
            "created_default_output": False,
            "config": config,
            "output_file": _get_output_file_state(m3u_file),
        }
    )

    _begin_job()
    try:
        output_dir = os.path.dirname(m3u_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if not os.path.exists(m3u_file):
            with open(m3u_file, "w", encoding="utf-8") as handle:
                handle.write("#EXTM3U\n")
            created_default_output = True

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["IPTV_API_URL"] = config["api_url"]
        env["IPTV_M3U_FILE"] = m3u_file
        env["IPTV_RTP_PREFIX"] = config["rtp_prefix"]
        env["IPTV_PLAYSEEK_PARAM"] = config["playseek_param"]

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            IPTV_SCRIPT,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise TimeoutError("Crawler timeout after 120 seconds") from exc

        stdout_text = _decode_output(stdout)
        stderr_text = _decode_output(stderr)

        if stdout_text:
            print(f"[Crawler stdout] {stdout_text}")
        if stderr_text:
            print(f"[Crawler stderr] {stderr_text}")

        if process.returncode != 0:
            error_tail = _tail_lines(stderr_text, limit=1) or _tail_lines(stdout_text, limit=1)
            message = error_tail[-1] if error_tail else "Crawler script failed"
            finished_at = datetime.now()
            _finalize_crawler_run(
                status="error",
                message=f"爬虫执行失败: {message}",
                started_at=started_at,
                finished_at=finished_at,
                return_code=process.returncode,
                stdout_text=stdout_text,
                stderr_text=stderr_text,
                import_stats={},
                trigger=trigger,
                created_default_output=created_default_output,
            )
            raise RuntimeError(message)

        import_stats = {"added": 0, "updated": 0, "unchanged": 0}
        if os.path.exists(m3u_file) and os.path.getsize(m3u_file) > 0:
            source_tag = config["source_tag"]
            async with AsyncSessionLocal() as db:
                crawler = ChannelCrawler(db)
                import_stats = await crawler.import_from_m3u_file(m3u_file, source_tag)

        finished_at = datetime.now()
        scheduler_state["import_stats"] = import_stats
        scheduler_state["last_import"] = finished_at
        message = "爬虫执行完成，频道已同步到数据库"
        if created_default_output:
            message = "爬虫执行完成，已自动创建默认输出文件并同步频道"
        if os.path.exists(m3u_file) and os.path.getsize(m3u_file) == 0:
            message = "爬虫执行完成，但输出文件为空"

        _finalize_crawler_run(
            status="success",
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            return_code=process.returncode,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
            import_stats=import_stats,
            trigger=trigger,
            created_default_output=created_default_output,
        )

        return {
            "status": "success",
            "message": message,
            "import_stats": import_stats,
            "timestamp": finished_at.isoformat(),
            "crawler": get_crawler_state(),
        }
    except TimeoutError:
        finished_at = datetime.now()
        _finalize_crawler_run(
            status="error",
            message="爬虫执行超时，120 秒内没有完成",
            started_at=started_at,
            finished_at=finished_at,
            return_code=None,
            stdout_text=stdout_text,
            stderr_text="Crawler timeout after 120 seconds",
            import_stats={},
            trigger=trigger,
            created_default_output=created_default_output,
        )
        raise
    except Exception as exc:
        if scheduler_state["crawler"]["running"]:
            finished_at = datetime.now()
            _finalize_crawler_run(
                status="error",
                message=f"爬虫执行失败: {exc}",
                started_at=started_at,
                finished_at=finished_at,
                return_code=None,
                stdout_text=stdout_text,
                stderr_text=str(exc),
                import_stats={},
                trigger=trigger,
                created_default_output=created_default_output,
            )
        raise
    finally:
        _finish_job()


async def auto_import_job():
    """Scheduled crawler run."""
    print("[...] Starting scheduled crawler...")
    try:
        await run_crawler_pipeline(trigger="scheduled")
        print("[OK] Scheduled crawler completed")
    except Exception as exc:
        print(f"[WARN] Scheduled crawler failed: {exc}")


def get_crawler_state():
    _refresh_crawler_snapshot()
    crawler_state = scheduler_state["crawler"]
    return {
        "status": crawler_state["status"],
        "running": crawler_state["running"],
        "trigger": crawler_state["trigger"],
        "message": crawler_state["message"],
        "last_started_at": _serialize_datetime(crawler_state["last_started_at"]),
        "last_finished_at": _serialize_datetime(crawler_state["last_finished_at"]),
        "last_success_at": _serialize_datetime(crawler_state["last_success_at"]),
        "duration_seconds": crawler_state["duration_seconds"],
        "return_code": crawler_state["return_code"],
        "stdout_tail": list(crawler_state["stdout_tail"]),
        "stderr_tail": list(crawler_state["stderr_tail"]),
        "log_tail": list(crawler_state["log_tail"]),
        "import_stats": dict(crawler_state["import_stats"]),
        "created_default_output": crawler_state["created_default_output"],
        "output_file": dict(crawler_state["output_file"]),
        "config": dict(crawler_state["config"]),
    }


def get_scheduler_state():
    """Get scheduler and crawler runtime state."""
    config = load_crawler_config()
    return {
        "is_running": scheduler_state["is_running"],
        "last_validation": _serialize_datetime(scheduler_state["last_validation"]),
        "last_import": _serialize_datetime(scheduler_state["last_import"]),
        "validation_stats": scheduler_state.get("validation_stats", {}),
        "import_stats": scheduler_state.get("import_stats", {}),
        "jobs": {
            "validation": _get_job_state("channel_validation", interval_hours=6),
            "crawler": _get_job_state("channel_crawler", interval_hours=config["interval_hours"]),
        },
        "crawler": get_crawler_state(),
    }


async def reload_crawler_schedule():
    """Apply the latest crawler interval without restarting the server."""
    config = load_crawler_config()
    if scheduler.get_job("channel_crawler"):
        scheduler.reschedule_job(
            "channel_crawler",
            trigger=IntervalTrigger(hours=config["interval_hours"]),
        )


async def start_scheduler():
    """Start the background scheduler."""
    config = load_crawler_config()
    scheduler.add_job(
        validate_all_job,
        trigger=IntervalTrigger(hours=6),
        id="channel_validation",
        name="Validate all channels",
        replace_existing=True,
    )

    scheduler.add_job(
        auto_import_job,
        trigger=IntervalTrigger(hours=config["interval_hours"]),
        id="channel_crawler",
        name="Run crawler and import channels",
        replace_existing=True,
    )

    scheduler.start()


async def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
