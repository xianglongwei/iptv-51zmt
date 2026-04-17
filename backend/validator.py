"""
Channel Validation Module
Health check engine for URL connectivity
Supports multiple detection methods: HTTP HEAD, GET, and stream probing
"""
import httpx
import asyncio
import subprocess
import re
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import ChannelPool


class ChannelValidator:
    """Channel health checker with multiple detection methods"""

    def __init__(self, db: AsyncSession, timeout: float = 10.0):
        self.db = db
        self.timeout = timeout

    async def check_url(self, url: str) -> Tuple[bool, Optional[int]]:
        """
        Check if URL is reachable using multiple methods
        Returns (is_active, latency_ms)
        """
        if not url:
            return False, None

        # Handle different URL types
        if url.startswith('rtp://') or url.startswith('udp://'):
            # For RTP/UDP, check if we can resolve the host
            return await self._check_rtp_url(url)
        
        if url.startswith('rtsp://'):
            return await self._check_rtsp_url(url)
        
        if url.startswith('http://') or url.startswith('https://'):
            return await self._check_http_url(url)
        
        # Unknown URL type - assume valid
        return True, None

    async def _check_rtp_url(self, url: str) -> Tuple[bool, Optional[int]]:
        """Check RTP/UDP URL by extracting host and port"""
        # Extract host and port from rtp://host:port or simple IP:PORT format
        match = re.search(r'rtp://([\d.]+):(\d+)', url) or re.search(r'([\d.]+):(\d+)$', url)
        if match:
            host = match.group(1)
            # Try to ping or check if host is reachable
            try:
                proc = await asyncio.create_subprocess_exec(
                    'ping', '-n', '1', '-w', '1000', host,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
                if proc.returncode == 0:
                    return True, None
            except:
                pass
        return True, None  # Assume valid for local streams

    async def _check_rtsp_url(self, url: str) -> Tuple[bool, Optional[int]]:
        """Check RTSP URL"""
        # Try a simple connection test
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # RTSP URLs often need DESCRIBE, but we can try HTTP fallback
                if 'http' in url:
                    response = await client.get(url, timeout=self.timeout)
                    return response.status_code < 400, None
        except:
            pass
        return True, None  # Assume valid

    async def _check_http_url(self, url: str) -> Tuple[bool, Optional[int]]:
        """
        Check HTTP/HTTPS URL with multiple strategies
        """
        # Strategy 1: Try HEAD request
        is_active, latency = await self._try_head(url)
        if is_active:
            return True, latency
        
        # Strategy 2: Try GET request with range header (for streaming)
        is_active, latency = await self._try_get_with_range(url)
        if is_active:
            return True, latency
        
        # Strategy 3: Try simple GET (last resort)
        is_active, latency = await self._try_get(url)
        
        return is_active, latency

    async def _try_head(self, url: str) -> Tuple[bool, Optional[int]]:
        """Try HEAD request"""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as client:
                start = datetime.now()
                response = await client.head(url)
                latency = int((datetime.now() - start).total_seconds() * 1000)
                
                if 200 <= response.status_code < 400:
                    return True, latency
        except:
            pass
        return False, None

    async def _try_get_with_range(self, url: str) -> Tuple[bool, Optional[int]]:
        """Try GET with Range header (works for streaming)"""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Range': 'bytes=0-32768'  # Request first 32KB
                }
            ) as client:
                start = datetime.now()
                async with client.stream("GET", url) as response:
                    latency = int((datetime.now() - start).total_seconds() * 1000)

                    # For streams, 200 or 206 is success
                    if response.status_code in (200, 206):
                        try:
                            await asyncio.wait_for(response.aread(), timeout=2)
                        except Exception:
                            pass
                        return True, latency

                    if 200 <= response.status_code < 400:
                        return True, latency
        except:
            pass
        return False, None

    async def _try_get(self, url: str) -> Tuple[bool, Optional[int]]:
        """Try simple GET request"""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            ) as client:
                start = datetime.now()
                response = await client.get(url, timeout=self.timeout)
                latency = int((datetime.now() - start).total_seconds() * 1000)
                
                if 200 <= response.status_code < 400:
                    return True, latency
        except:
            pass
        return False, None

    async def check_channel(self, channel: ChannelPool) -> Tuple[bool, Optional[int]]:
        """Check single channel and update database"""
        is_active, latency = await self.check_url(channel.live_url)

        channel.is_active = is_active
        channel.last_check = datetime.now()
        channel.latency_ms = latency

        return is_active, latency

    async def check_all_channels(self, batch_size: int = 30) -> dict:
        """Check all channels in database"""
        stmt = select(ChannelPool)
        result = await self.db.execute(stmt)
        channels = result.scalars().all()

        stats = {"total": len(channels), "online": 0, "offline": 0, "checked": 0}

        for i in range(0, len(channels), batch_size):
            batch = channels[i:i + batch_size]

            tasks = [self.check_channel(ch) for ch in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for ch, result in zip(batch, results):
                if isinstance(result, Exception):
                    ch.is_active = False
                    ch.latency_ms = None
                    stats["offline"] += 1
                elif result[0]:
                    stats["online"] += 1
                else:
                    stats["offline"] += 1
                stats["checked"] += 1

            await self.db.commit()
            await asyncio.sleep(1)  # Delay between batches

        return stats

    async def check_channel_by_id(self, channel_id: int) -> dict:
        """Check single channel by ID"""
        stmt = select(ChannelPool).where(ChannelPool.id == channel_id)
        result = await self.db.execute(stmt)
        channel = result.scalar_one_or_none()

        if not channel:
            return {"error": "Channel not found"}

        is_active, latency = await self.check_channel(channel)
        await self.db.commit()

        return {
            "channel_id": channel_id,
            "is_active": is_active,
            "latency_ms": latency,
            "last_check": channel.last_check.isoformat() if channel.last_check else None
        }
