"""
M3U Output Generator
Generates dynamic M3U playlist from selected channels
"""
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ChannelPool, SelectedChannel
from backend.m3u_parser import generate_m3u_content


class M3uGenerator:
    """M3U playlist generator"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_selected_m3u(
        self,
        use_catchup: bool = True,
        rtp_prefix: str = "http://192.168.10.1:10000/rtp/"
    ) -> str:
        """
        Generate M3U from selected channels
        """
        # Get selected channels with pool info
        stmt = select(SelectedChannel, ChannelPool).join(
            ChannelPool, SelectedChannel.pool_id == ChannelPool.id
        ).order_by(SelectedChannel.sort_order)

        result = await self.db.execute(stmt)
        rows = result.all()

        channels = []
        for selected, pool in rows:
            ch = {
                'tvg_name': pool.tvg_name,
                'tvg_logo': pool.tvg_logo,
                'group_title': pool.group_title,
                'live_url': pool.live_url,
                'custom_name': selected.custom_name or pool.tvg_name,
            }

            # Respect the per-channel publish setting when generating catchup fields.
            if use_catchup and selected.catchup_enabled and pool.catchup_source:
                ch['catchup_source'] = pool.catchup_source
            else:
                ch['catchup_source'] = ''

            channels.append(ch)

        return generate_m3u_content(channels, use_catchup=use_catchup, rtp_prefix=rtp_prefix)

    async def generate_all_active_m3u(
        self,
        use_catchup: bool = False,
        rtp_prefix: str = "http://192.168.10.1:10000/rtp/"
    ) -> str:
        """
        Generate M3U from all active channels
        """
        stmt = select(ChannelPool).where(ChannelPool.is_active == True).order_by(
            ChannelPool.group_title, ChannelPool.tvg_name
        )
        result = await self.db.execute(stmt)
        channels = result.scalars().all()

        channel_list = []
        for ch in channels:
            channel_list.append({
                'tvg_name': ch.tvg_name,
                'tvg_logo': ch.tvg_logo,
                'group_title': ch.group_title,
                'live_url': ch.live_url,
                'catchup_source': ch.catchup_source if use_catchup else '',
            })

        return generate_m3u_content(channel_list, use_catchup=use_catchup, rtp_prefix=rtp_prefix)

    async def generate_group_m3u(
        self,
        group_title: str,
        use_catchup: bool = False,
        rtp_prefix: str = "http://192.168.10.1:10000/rtp/"
    ) -> str:
        """
        Generate M3U for specific group
        """
        stmt = select(ChannelPool).where(
            ChannelPool.group_title == group_title,
            ChannelPool.is_active == True
        ).order_by(ChannelPool.tvg_name)

        result = await self.db.execute(stmt)
        channels = result.scalars().all()

        channel_list = []
        for ch in channels:
            channel_list.append({
                'tvg_name': ch.tvg_name,
                'tvg_logo': ch.tvg_logo,
                'group_title': ch.group_title,
                'live_url': ch.live_url,
                'catchup_source': ch.catchup_source if use_catchup else '',
            })

        return generate_m3u_content(channel_list, use_catchup=use_catchup, rtp_prefix=rtp_prefix)
