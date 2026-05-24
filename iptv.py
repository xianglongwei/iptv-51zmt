import os
import re
import sys
from dataclasses import dataclass

import requests


API_URL = os.getenv("IPTV_API_URL", "https://epg.51zmt.top:8001/multicast/api/channels/1/")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.getenv("IPTV_DATA_DIR", PROJECT_ROOT))
M3U_FILE = os.getenv("IPTV_M3U_FILE", os.path.join(DATA_DIR, "2.m3u"))
RTP_PREFIX = os.getenv("IPTV_RTP_PREFIX", "http://192.168.10.1:10000/rtp/")
PLAYSEEK_PARAM = os.getenv(
    "IPTV_PLAYSEEK_PARAM",
    "?playseek=${(b)yyyyMMddHHmmss}-${(e)yyyyMMddHHmmss}",
)


@dataclass
class ProcessStats:
    updated: int = 0
    added: int = 0
    unchanged: int = 0


def get_online_data() -> list[dict]:
    """Fetch online channel data from the configured multicast API."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://epg.51zmt.top:8001/multicast/",
    }
    response = requests.get(API_URL, headers=headers, timeout=20)
    response.raise_for_status()

    payload = response.json()
    channels = payload.get("channels", [])
    if not isinstance(channels, list):
        raise RuntimeError("API 返回格式不正确：channels 不是列表")
    if not channels:
        raise RuntimeError("API 没有返回任何频道数据")
    return channels


def parse_local_m3u(file_path: str) -> list[dict]:
    with open(file_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    items = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("#EXTINF"):
            name = line.split(",", 1)[-1].strip()
            url = lines[index + 1].strip() if index + 1 < len(lines) else ""
            items.append({"info": line, "url": url, "name": name})
            index += 2
            continue

        if line and not line.startswith("#EXTM3U"):
            items.append({"raw": lines[index]})
        index += 1
    return items


def append_playseek(replay_url: str) -> str:
    replay_url = (replay_url or "").strip()
    if replay_url and PLAYSEEK_PARAM not in replay_url:
        return f"{replay_url}{PLAYSEEK_PARAM}"
    return replay_url


def update_catchup_source(info_line: str, channel_name: str, replay_url: str) -> str:
    if not replay_url:
        return info_line
    if 'catchup-source="' in info_line:
        return re.sub(r'catchup-source="[^"]*"', f'catchup-source="{replay_url}"', info_line)
    return info_line.replace(f",{channel_name}", f' catchup-source="{replay_url}",{channel_name}')


def build_new_entry(channel_name: str, url: str, replay_url: str) -> dict:
    info = (
        f'#EXTINF:-1 tvg-name="{channel_name}" '
        f'group-title="卫视" catchup-source="{replay_url}",{channel_name}'
    )
    return {"info": info, "url": url, "name": channel_name}


def process_m3u() -> ProcessStats:
    online_list = get_online_data()

    if not os.path.exists(M3U_FILE):
        raise FileNotFoundError(f"找不到 M3U 文件: {M3U_FILE}")

    m3u_items = parse_local_m3u(M3U_FILE)
    stats = ProcessStats()

    for online in online_list:
        channel_name = str(online.get("channel_name", "")).strip()
        multicast_address = str(online.get("multicast_address", "")).strip()
        if not channel_name or not multicast_address:
            stats.unchanged += 1
            continue

        replay_url = append_playseek(str(online.get("replay_url", "")).strip())
        new_url = f"{RTP_PREFIX}{multicast_address}"
        match = next((item for item in m3u_items if item.get("name") == channel_name), None)

        if match:
            next_info = update_catchup_source(match["info"], channel_name, replay_url)
            changed = match.get("url") != new_url or match.get("info") != next_info
            match["url"] = new_url
            match["info"] = next_info
            if changed:
                stats.updated += 1
                print(f"【已更新】 {channel_name}")
            else:
                stats.unchanged += 1
            continue

        if "4K" not in channel_name and "UHD" not in channel_name:
            stats.unchanged += 1
            continue

        base_name = channel_name.replace("4K", "").replace("UHD", "").strip()
        insert_pos = -1
        for index, item in enumerate(m3u_items):
            if item.get("name") and base_name in item["name"]:
                insert_pos = index

        new_entry = build_new_entry(channel_name, new_url, replay_url)
        if insert_pos != -1:
            m3u_items.insert(insert_pos + 1, new_entry)
            print(f"【已插入】 {channel_name} (紧跟 {m3u_items[insert_pos]['name']})")
        else:
            m3u_items.append(new_entry)
            print(f"【已添加】 {channel_name} (末尾)")
        stats.added += 1

    with open(M3U_FILE, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("#EXTM3U\n")
        for item in m3u_items:
            if "raw" in item:
                handle.write(item["raw"])
            else:
                handle.write(item["info"] + "\n")
                handle.write(item["url"] + "\n")

    print(
        f"\n所有操作已完成。更新 {stats.updated} 个，新增 {stats.added} 个，"
        f"未变化/跳过 {stats.unchanged} 个。"
    )
    return stats


if __name__ == "__main__":
    try:
        process_m3u()
    except Exception as exc:
        print(f"爬取失败: {exc}", file=sys.stderr)
        sys.exit(1)
