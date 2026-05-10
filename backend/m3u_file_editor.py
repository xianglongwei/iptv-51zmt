"""Helpers for editing the repository's 2.m3u playlist file."""
import os
import re
import tempfile
from typing import Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M3U_FILE = os.path.join(PROJECT_ROOT, "2.m3u")


def read_m3u_lines() -> list[str]:
    """Read 2.m3u with common playlist encodings."""
    encodings = ("utf-8-sig", "utf-8", "gb18030", "gbk")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            with open(M3U_FILE, "r", encoding=encoding) as handle:
                return handle.read().splitlines()
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def write_m3u_lines(lines: list[str]) -> None:
    """Atomically write normalized M3U lines back to 2.m3u."""
    content = "\n".join(lines).rstrip() + "\n"
    directory = os.path.dirname(M3U_FILE)
    fd, temp_path = tempfile.mkstemp(prefix="2.", suffix=".m3u.tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temp_path, M3U_FILE)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def parse_extinf_attrs(line: str) -> tuple[dict[str, str], str]:
    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', line))
    display_name = line.split(",", 1)[1].strip() if "," in line else attrs.get("tvg-name", "")
    return attrs, display_name


def build_extinf_line(channel: dict[str, Any]) -> str:
    attrs = []
    for key in ("tvg-id", "tvg-name", "tvg-logo", "group-title", "catchup", "catchup-source"):
        value = str(channel.get(key) or "").strip()
        if value:
            attrs.append(f'{key}="{value.replace(chr(34), "")}"')
    name = str(channel.get("name") or channel.get("tvg-name") or "未命名频道").strip()
    attr_text = f" {' '.join(attrs)}" if attrs else ""
    return f"#EXTINF:-1{attr_text},{name}"


def parse_m3u_channels() -> list[dict[str, Any]]:
    if not os.path.exists(M3U_FILE):
        return []

    lines = read_m3u_lines()
    channels = []
    line_index = 0
    channel_number = 0
    while line_index < len(lines):
        line = lines[line_index].strip()
        if line.startswith("#EXTINF"):
            attrs, name = parse_extinf_attrs(line)
            url_index = line_index + 1
            url = ""
            while url_index < len(lines):
                candidate = lines[url_index].strip()
                if candidate and not candidate.startswith("#"):
                    url = candidate
                    break
                if candidate.startswith("#EXTINF"):
                    break
                url_index += 1

            channels.append(
                {
                    "id": line_index,
                    "index": channel_number,
                    "extinf_line": line,
                    "url_line": url_index if url else None,
                    "name": name,
                    "tvg_name": attrs.get("tvg-name", name),
                    "tvg_logo": attrs.get("tvg-logo", ""),
                    "group": attrs.get("group-title", "未分组"),
                    "catchup": attrs.get("catchup", ""),
                    "catchup_source": attrs.get("catchup-source", ""),
                    "url": url,
                    "attrs": attrs,
                }
            )
            channel_number += 1
            line_index = max(url_index + 1, line_index + 1)
        else:
            line_index += 1
    return channels


def find_channel_line(lines: list[str], channel_id: int) -> tuple[int, int]:
    if channel_id < 0 or channel_id >= len(lines) or not lines[channel_id].strip().startswith("#EXTINF"):
        raise ValueError("未找到对应频道")

    url_index = channel_id + 1
    while url_index < len(lines):
        candidate = lines[url_index].strip()
        if candidate and not candidate.startswith("#"):
            return channel_id, url_index
        if candidate.startswith("#EXTINF"):
            break
        url_index += 1
    return channel_id, channel_id + 1


def normalize_channel_payload(data: dict[str, Any]) -> dict[str, str]:
    name = str(data.get("name") or data.get("tvg_name") or "").strip()
    url = str(data.get("url") or "").strip()
    if not name:
        raise ValueError("频道名称不能为空")
    if not url:
        raise ValueError("播放地址不能为空")
    return {
        "name": name,
        "tvg-name": str(data.get("tvg_name") or name).strip(),
        "tvg-logo": str(data.get("tvg_logo") or data.get("logo") or "").strip(),
        "group-title": str(data.get("group") or data.get("group_title") or "未分组").strip(),
        "catchup": str(data.get("catchup") or "").strip(),
        "catchup-source": str(data.get("catchup_source") or "").strip(),
        "url": url,
    }


def create_channel(data: dict[str, Any]) -> dict[str, Any] | None:
    payload = normalize_channel_payload(data)
    lines = read_m3u_lines() if os.path.exists(M3U_FILE) else ["#EXTM3U"]
    if not lines or not lines[0].startswith("#EXTM3U"):
        lines.insert(0, "#EXTM3U")
    lines.extend([build_extinf_line(payload), payload["url"]])
    write_m3u_lines(lines)
    channels = parse_m3u_channels()
    return channels[-1] if channels else None


def update_channel(channel_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    payload = normalize_channel_payload(data)
    lines = read_m3u_lines()
    extinf_index, url_index = find_channel_line(lines, channel_id)
    lines[extinf_index] = build_extinf_line(payload)
    if url_index < len(lines):
        lines[url_index] = payload["url"]
    else:
        lines.append(payload["url"])
    write_m3u_lines(lines)
    return next((item for item in parse_m3u_channels() if item["id"] == channel_id), None)


def delete_channel(channel_id: int) -> int:
    lines = read_m3u_lines()
    extinf_index, url_index = find_channel_line(lines, channel_id)
    del lines[extinf_index : url_index + 1]
    write_m3u_lines(lines)
    return len(parse_m3u_channels())
