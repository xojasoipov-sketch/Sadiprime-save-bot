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
        # datacenter/VPS IPs — and as of 2025-2026 this has escalated to
        # requiring a PO (proof-of-origin) token for a growing share of
        # requests, including on the "android" client that used to dodge
        # it reliably (see yt-dlp/yt-dlp#17348). "tv" is the current
        # community-recommended first try since it needs a PO token the
        # least often of the no-login clients; "android" and "web" stay
        # as a fallback chain. No client list is a permanent fix — if
        # BotDetectionError keeps recurring, YouTube cookies in the same
        # COOKIES_FILE (README "Instagram cookies") are the durable
        # mitigation, same as Instagram's anti-bot wall.
        "extractor_args": {"youtube": {"player_client": ["tv", "android", "web"]}},
    }

    def can_handle(self, url: str) -> bool:
        return any(domain in url for domain in PLATFORM_DOMAINS["youtube"])
