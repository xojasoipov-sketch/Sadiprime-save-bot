"""Adapter registry — maps a security-validated URL to its adapter.

Adding a future platform (Twitter, Facebook, Reddit, ...) means:
  1. add its domains to core.security.PLATFORM_DOMAINS
  2. write a new `downloader/<platform>.py` adapter
  3. register it in `_ADAPTERS` below

Nothing else in the bot/worker changes.
"""

from __future__ import annotations

from core.security import InvalidUrlError, ValidatedUrl, normalize_and_validate_url
from downloader.base import DownloaderAdapter, UnsupportedPlatformError
from downloader.instagram import InstagramAdapter
from downloader.music_search import SEARCH_PLATFORM, MusicSearchAdapter
from downloader.pinterest import PinterestAdapter
from downloader.tiktok import TikTokAdapter
from downloader.youtube import YouTubeAdapter

_ADAPTERS: dict[str, DownloaderAdapter] = {
    "instagram": InstagramAdapter(),
    "tiktok": TikTokAdapter(),
    "youtube": YouTubeAdapter(),
    "pinterest": PinterestAdapter(),
}

# Not URL-domain-triggered, so kept out of _ADAPTERS/supported_platforms()
# (which describe what detect_platform() can match a link against) — see
# downloader/music_search.py and bot/handlers/download.py for how a plain
# text message routes here instead.
_SEARCH_ADAPTERS: dict[str, DownloaderAdapter] = {
    SEARCH_PLATFORM: MusicSearchAdapter(),
}


def detect_platform(url: str, *, check_dns: bool = True) -> ValidatedUrl:
    """Validate + normalize the URL and identify its platform.

    Raises core.security.InvalidUrlError for anything malformed/unsafe,
    or UnsupportedPlatformError if the domain is valid but has no
    registered adapter.
    """

    validated = normalize_and_validate_url(url, check_dns=check_dns)
    if validated.platform not in _ADAPTERS:
        raise UnsupportedPlatformError(f"No adapter registered for {validated.platform}")
    return validated


def get_adapter(platform: str) -> DownloaderAdapter:
    adapter = _ADAPTERS.get(platform) or _SEARCH_ADAPTERS.get(platform)
    if adapter is None:
        raise UnsupportedPlatformError(f"No adapter registered for {platform}")
    return adapter


def supported_platforms() -> list[str]:
    return sorted(_ADAPTERS.keys())


__all__ = [
    "InvalidUrlError",
    "detect_platform",
    "get_adapter",
    "supported_platforms",
]
