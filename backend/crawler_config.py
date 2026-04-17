"""
Crawler configuration loader/saver.

Persists user overrides in crawler_config.json while keeping iptv.py defaults
as the fallback baseline.
"""
import importlib.util
import json
import os
from typing import Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IPTV_SCRIPT = os.path.join(PROJECT_ROOT, "iptv.py")
CONFIG_PATH = os.path.join(PROJECT_ROOT, "crawler_config.json")
DEFAULT_INTERVAL_HOURS = 12
DEFAULT_SOURCE_TAG = "爬虫默认源"


def _load_script_defaults() -> dict[str, Any]:
    defaults = {
        "api_url": "https://epg.51zmt.top:8001/multicast/api/channels/1/",
        "m3u_file": "2.m3u",
        "rtp_prefix": "http://192.168.10.1:10000/rtp/",
        "playseek_param": "?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}",
        "interval_hours": DEFAULT_INTERVAL_HOURS,
        "source_tag": DEFAULT_SOURCE_TAG,
    }

    if not os.path.exists(IPTV_SCRIPT):
        return defaults

    spec = importlib.util.spec_from_file_location("lumina_iptv_defaults", IPTV_SCRIPT)
    if not spec or not spec.loader:
        return defaults

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    defaults.update(
        {
            "api_url": getattr(module, "API_URL", defaults["api_url"]),
            "m3u_file": getattr(module, "M3U_FILE", defaults["m3u_file"]),
            "rtp_prefix": getattr(module, "RTP_PREFIX", defaults["rtp_prefix"]),
            "playseek_param": getattr(module, "PLAYSEEK_PARAM", defaults["playseek_param"]),
        }
    )
    return defaults


def _load_saved_config() -> tuple[dict[str, Any], str | None]:
    if not os.path.exists(CONFIG_PATH):
        return {}, None

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}, None
    except Exception as exc:
        return {}, str(exc)


def _normalize_m3u_path(path: str) -> str:
    value = (path or "").strip() or "2.m3u"
    return value


def resolve_m3u_path(path: str) -> str:
    value = _normalize_m3u_path(path)
    if os.path.isabs(value):
        return value
    return os.path.join(PROJECT_ROOT, value)


def _build_note(using_saved_config: bool, load_error: str | None) -> str:
    if load_error:
        return f"配置文件读取失败，已回退到默认参数。错误: {load_error}"
    if using_saved_config:
        return "当前使用你在界面中保存的爬虫配置。"
    return "当前没有单独保存的配置，爬虫使用 iptv.py 内置默认参数。"


def load_crawler_config() -> dict[str, Any]:
    defaults = _load_script_defaults()
    saved, load_error = _load_saved_config()
    config = {**defaults, **saved}

    interval_hours = saved.get("interval_hours", defaults["interval_hours"])
    try:
        interval_hours = int(interval_hours)
    except (TypeError, ValueError):
        interval_hours = defaults["interval_hours"]
    interval_hours = min(max(interval_hours, 1), 168)

    m3u_file = _normalize_m3u_path(str(config.get("m3u_file", defaults["m3u_file"])))

    return {
        "api_url": str(config.get("api_url", defaults["api_url"])).strip(),
        "m3u_file": m3u_file,
        "resolved_m3u_file": resolve_m3u_path(m3u_file),
        "rtp_prefix": str(config.get("rtp_prefix", defaults["rtp_prefix"])).strip(),
        "playseek_param": str(config.get("playseek_param", defaults["playseek_param"])).strip(),
        "interval_hours": interval_hours,
        "source_tag": str(config.get("source_tag", defaults["source_tag"])).strip() or DEFAULT_SOURCE_TAG,
        "using_saved_config": os.path.exists(CONFIG_PATH) and not load_error,
        "config_file_path": CONFIG_PATH if os.path.exists(CONFIG_PATH) else None,
        "load_error": load_error,
        "note": _build_note(os.path.exists(CONFIG_PATH) and not load_error, load_error),
    }


def save_crawler_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_crawler_config()
    merged = {
        "api_url": str(payload.get("api_url", current["api_url"])).strip(),
        "m3u_file": _normalize_m3u_path(str(payload.get("m3u_file", current["m3u_file"]))),
        "rtp_prefix": str(payload.get("rtp_prefix", current["rtp_prefix"])).strip(),
        "playseek_param": str(payload.get("playseek_param", current["playseek_param"])).strip(),
        "interval_hours": payload.get("interval_hours", current["interval_hours"]),
        "source_tag": str(payload.get("source_tag", current["source_tag"])).strip() or DEFAULT_SOURCE_TAG,
    }

    try:
        merged["interval_hours"] = int(merged["interval_hours"])
    except (TypeError, ValueError) as exc:
        raise ValueError("定时爬取间隔必须是数字") from exc

    if not merged["api_url"]:
        raise ValueError("API 地址不能为空")
    if not merged["m3u_file"]:
        raise ValueError("输出文件不能为空")
    if merged["interval_hours"] < 1 or merged["interval_hours"] > 168:
        raise ValueError("定时爬取间隔需要在 1 到 168 小时之间")

    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)

    return load_crawler_config()
