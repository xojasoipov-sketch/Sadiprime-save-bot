"""Instagram adapter — reels, posts, videos, images, carousels.

Only publicly accessible posts are supported. Private-account content is
not accessible without authentication, and we deliberately do not attempt
to bypass that (see project policy in README "Copyright / Compliance").
"""

from __future__ import annotations

from core.security import PLATFORM_DOMAINS
from downloader._ytdlp_common import YtDlpAdapter


class InstagramAdapter(YtDlpAdapter):
    name = "instagram"

    # Carousels come back from yt-dlp as a multi-entry "playlist" for a
    # single post URL; we want every item, so unlike other platforms we
    # allow yt-dlp's internal multi-entry extraction for Instagram posts.
    extra_ydl_opts = {"noplaylist": False}

    def can_handle(self, url: str) -> bool:
        return any(domain in url for domain in PLATFORM_DOMAINS["instagram"])
