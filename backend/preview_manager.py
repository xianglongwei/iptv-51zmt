"""
Preview session manager.
Uses FFmpeg to convert live IPTV sources into short HLS playlists
that browsers can preview reliably.
"""
import asyncio
import hashlib
import os
import shutil
import time
from dataclasses import dataclass, field


@dataclass
class PreviewSession:
    session_id: str
    url: str
    directory: str
    playlist_path: str
    process: asyncio.subprocess.Process | None = None
    started_at: float = field(default_factory=time.time)


class PreviewManager:
    def __init__(self, cache_root: str):
        self.cache_root = cache_root
        self.sessions: dict[str, PreviewSession] = {}
        self.lock = asyncio.Lock()
        os.makedirs(self.cache_root, exist_ok=True)

    async def start_session(self, url: str) -> PreviewSession:
        session_id = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]

        async with self.lock:
            await self._cleanup_finished()

            existing = self.sessions.get(session_id)
            if existing and existing.process and existing.process.returncode is None:
                return existing

            for other_id in list(self.sessions.keys()):
                await self._stop_session(other_id)

            session_dir = os.path.join(self.cache_root, session_id)
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir, ignore_errors=True)
            os.makedirs(session_dir, exist_ok=True)

            playlist_path = os.path.join(session_dir, "index.m3u8")
            segment_pattern = os.path.join(session_dir, "segment_%03d.ts")

            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-fflags",
                "+genpts",
                "-i",
                url,
                "-map",
                "0:v:0?",
                "-map",
                "0:a:0?",
                "-sn",
                "-dn",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "zerolatency",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "scale=-2:720",
                "-g",
                "50",
                "-keyint_min",
                "50",
                "-sc_threshold",
                "0",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-max_muxing_queue_size",
                "1024",
                "-f",
                "hls",
                "-hls_time",
                "2",
                "-hls_list_size",
                "15",
                "-hls_flags",
                "append_list+omit_endlist+independent_segments+program_date_time",
                "-hls_segment_filename",
                segment_pattern,
                playlist_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            session = PreviewSession(
                session_id=session_id,
                url=url,
                directory=session_dir,
                playlist_path=playlist_path,
                process=process,
            )
            self.sessions[session_id] = session

        ready = await self._wait_for_playlist(session)
        if not ready:
            error = await self._collect_error(session)
            await self.stop_session(session.session_id)
            raise RuntimeError(error or "FFmpeg preview startup timed out")

        return session

    async def stop_session(self, session_id: str):
        async with self.lock:
            await self._stop_session(session_id)

    async def shutdown(self):
        async with self.lock:
            for session_id in list(self.sessions.keys()):
                await self._stop_session(session_id)

    async def _cleanup_finished(self):
        for session_id, session in list(self.sessions.items()):
            if session.process and session.process.returncode is not None:
                await self._stop_session(session_id)

    async def _stop_session(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if not session:
            return

        if session.process and session.process.returncode is None:
            session.process.kill()
            try:
                await asyncio.wait_for(session.process.wait(), timeout=3)
            except asyncio.TimeoutError:
                pass

        shutil.rmtree(session.directory, ignore_errors=True)

    async def _wait_for_playlist(self, session: PreviewSession, timeout: float = 12.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if os.path.exists(session.playlist_path) and os.path.getsize(session.playlist_path) > 0:
                return True
            if session.process and session.process.returncode is not None:
                return False
            await asyncio.sleep(0.4)
        return False

    async def _collect_error(self, session: PreviewSession) -> str:
        if not session.process or not session.process.stderr:
            return ""
        try:
            output = await asyncio.wait_for(session.process.stderr.read(), timeout=1)
        except asyncio.TimeoutError:
            return ""
        return output.decode("utf-8", errors="ignore").strip()
