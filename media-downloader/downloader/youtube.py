"""YouTube adapter — normal videos and Shorts.

Playlists are never expanded (noplaylist=True from the shared base): a
single video/Shorts URL always yields exactly one media item, per spec.
"""

from __future__ import annotations

from core.security import PLATFORM_DOMAINS
from downloader._ytdlp_common import YtDlpAdapter


class YouTubeAdapter(YtDlpAdapter):
    name = "youtube"

    extra_ydl_opts = {
        "noplaylist": True,
    }

    def can_handle(self, url: str) -> bool:
        return any(domain in url for domain in PLATFORM_DOMAINS["youtube"])
