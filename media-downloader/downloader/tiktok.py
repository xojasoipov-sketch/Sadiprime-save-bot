"""TikTok adapter — public videos, including short vm./vt. links."""

from __future__ import annotations

from core.security import PLATFORM_DOMAINS
from downloader._ytdlp_common import YtDlpAdapter


class TikTokAdapter(YtDlpAdapter):
    name = "tiktok"

    extra_ydl_opts = {
        # TikTok's own watermark-free extraction is handled by yt-dlp's
        # extractor already; nothing platform-specific required beyond
        # sane defaults from the shared base.
    }

    def can_handle(self, url: str) -> bool:
        return any(domain in url for domain in PLATFORM_DOMAINS["tiktok"])
