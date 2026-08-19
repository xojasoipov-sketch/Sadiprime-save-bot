"""Pinterest adapter — public pins (pin.it short links and pinterest.com)."""

from __future__ import annotations

from core.security import PLATFORM_DOMAINS
from downloader._ytdlp_common import YtDlpAdapter


class PinterestAdapter(YtDlpAdapter):
    name = "pinterest"

    def can_handle(self, url: str) -> bool:
        return any(domain in url for domain in PLATFORM_DOMAINS["pinterest"])
