"""
Published playlist configuration.

Stores the user-facing exported playlist filename for the selected-channel
playlist while keeping a safe default.
"""
import json
import os
import re
from typing import Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "published_config.json")
DEFAULT_PLAYLIST_FILENAME = "my_list.m3u"
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def normalize_playlist_filename(value: str | None) -> str:
    filename = os.path.basename((value or "").strip()) or DEFAULT_PLAYLIST_FILENAME
    if not filename.lower().endswith(".m3u"):
        filename = f"{filename}.m3u"
    if not SAFE_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("Playlist filename may only contain letters, numbers, dot, dash, and underscore")
    return filename


def load_published_config() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                payload = data
        except Exception:
            payload = {}

    filename = normalize_playlist_filename(payload.get("playlist_filename"))
    return {
        "playlist_filename": filename,
        "playlist_path": f"/playlist/{filename}",
        "legacy_playlist_path": f"/{DEFAULT_PLAYLIST_FILENAME}",
        "config_file_path": CONFIG_PATH if os.path.exists(CONFIG_PATH) else None,
    }


def save_published_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_published_config()
    config = {
        "playlist_filename": normalize_playlist_filename(
            payload.get("playlist_filename", current["playlist_filename"])
        )
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
    return load_published_config()
