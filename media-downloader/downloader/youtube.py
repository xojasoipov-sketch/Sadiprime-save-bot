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
        # YouTube increasingly blocks the default "web" client with
        # "Sign in to confirm you're not a bot", especially from
        # datacenter/VPS IPs. The "android" client is less aggressively
        # flagged and doesn't need a PO token; "web" stays as a fallback
        # for anything android can't extract. See downloader/base.py's
        # BotDetectionError docstring for the error-handling side of this.
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }

    def can_handle(self, url: str) -> bool:
        return any(domain in url for domain in PLATFORM_DOMAINS["youtube"])
