"""
Channel Crawler Module
Handles importing channels from M3U files and URLs
"""
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ChannelPool
from backend.m3u_parser import match_catchup_template, parse_m3u_content, parse_m3u_file


class ChannelCrawler:
    """Channel crawler and importer."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_from_m3u_file(self, file_path: str, source_tag: str = "本地文件") -> dict:
        channels = parse_m3u_file(file_path)
        stats = {"added": 0, "updated": 0, "unchanged": 0}

        for channel in channels:
            action = await self._upsert_channel(channel, source_tag)
            stats[action] += 1

        await self.db.commit()
        return stats

    async def import_from_m3u_url(self, url: str, source_tag: str = "网络订阅") -> dict:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return {"error": str(exc)}

        channels = parse_m3u_content(response.text)
        stats = {"added": 0, "updated": 0, "unchanged": 0}
        for channel in channels:
            action = await self._upsert_channel(channel, source_tag)
            stats[action] += 1

        await self.db.commit()
        stats["imported"] = len(channels)
        return stats

    async def import_from_web(self, url: str, source_tag: str = "网页抓取") -> dict:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if ".m3u" not in href.lower():
                    continue
                if not href.startswith("http"):
                    from urllib.parse import urljoin

                    href = urljoin(url, href)
                return await self.import_from_m3u_url(href, source_tag)
        except Exception as exc:
            return {"error": str(exc)}

        return {"error": "未找到可导入的 M3U 链接"}

    async def _upsert_channel(self, channel_data: dict, source_tag: str) -> str:
        live_url = channel_data.get("live_url", "").strip()
        if not live_url:
            return "unchanged"

        result = await self.db.execute(select(ChannelPool).where(ChannelPool.live_url == live_url))
        existing = result.scalar_one_or_none()
        now = datetime.now()

        if existing:
            changed = False
            fields = (
                ("tvg_name", channel_data.get("tvg_name") or existing.tvg_name),
                ("tvg_logo", channel_data.get("tvg_logo") or existing.tvg_logo),
                ("group_title", channel_data.get("group_title") or existing.group_title),
                ("source_tag", source_tag),
            )
            for field_name, next_value in fields:
                if getattr(existing, field_name) != next_value:
                    setattr(existing, field_name, next_value)
                    changed = True

            catchup_source = channel_data.get("catchup_source")
            catchup_type = channel_data.get("catchup_type")
            if catchup_source and existing.catchup_source != catchup_source:
                existing.catchup_source = catchup_source
                changed = True
            if catchup_type and existing.catchup_type != catchup_type:
                existing.catchup_type = catchup_type
                changed = True

            if changed:
                existing.updated_at = now
                return "updated"
            return "unchanged"

        catchup_source = channel_data.get("catchup_source", "")
        catchup_type = channel_data.get("catchup_type", "")
        if not catchup_source:
            matched = match_catchup_template(live_url)
            if matched:
                catchup_source = matched.get("catchup_source", "")
                catchup_type = matched.get("catchup_type", "")

        self.db.add(
            ChannelPool(
                tvg_name=channel_data.get("tvg_name", ""),
                tvg_logo=channel_data.get("tvg_logo", ""),
                group_title=channel_data.get("group_title", ""),
                live_url=live_url,
                catchup_type=catchup_type,
                catchup_source=catchup_source,
                is_active=True,
                last_check=now,
                source_tag=source_tag,
                created_at=now,
                updated_at=now,
            )
        )
        return "added"

    async def get_all_channels(self) -> list:
        result = await self.db.execute(
            select(ChannelPool).order_by(ChannelPool.group_title, ChannelPool.tvg_name)
        )
        return result.scalars().all()

    async def get_channel_by_id(self, channel_id: int) -> ChannelPool:
        result = await self.db.execute(select(ChannelPool).where(ChannelPool.id == channel_id))
        return result.scalar_one_or_none()

    async def get_active_channels(self) -> list:
        result = await self.db.execute(
            select(ChannelPool)
            .where(ChannelPool.is_active.is_(True))
            .order_by(ChannelPool.group_title, ChannelPool.tvg_name)
        )
        return result.scalars().all()

    async def get_channels_by_group(self, group: str) -> list:
        result = await self.db.execute(
            select(ChannelPool)
            .where(ChannelPool.group_title == group)
            .order_by(ChannelPool.tvg_name)
        )
        return result.scalars().all()

    async def get_groups(self) -> list:
        result = await self.db.execute(
            select(ChannelPool.group_title)
            .distinct()
            .where(ChannelPool.group_title.is_not(None))
            .order_by(ChannelPool.group_title)
        )
        return [row[0] for row in result.all() if row[0]]
