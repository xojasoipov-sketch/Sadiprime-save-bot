from __future__ import annotations

import pytest

from core.security import InvalidUrlError
from downloader.base import UnsupportedPlatformError
from downloader.instagram import InstagramAdapter
from downloader.pinterest import PinterestAdapter
from downloader.registry import detect_platform, get_adapter, supported_platforms
from downloader.tiktok import TikTokAdapter
from downloader.youtube import YouTubeAdapter


class TestPlatformDetection:
    @pytest.mark.parametrize(
        ("url", "platform", "adapter_cls"),
        [
            ("https://www.instagram.com/reel/xyz/", "instagram", InstagramAdapter),
            ("https://www.tiktok.com/@u/video/1", "tiktok", TikTokAdapter),
            ("https://youtu.be/abc123", "youtube", YouTubeAdapter),
            ("https://pin.it/abc", "pinterest", PinterestAdapter),
        ],
    )
    def test_detects_and_selects_adapter(self, url, platform, adapter_cls):
        validated = detect_platform(url, check_dns=False)
        assert validated.platform == platform

        adapter = get_adapter(validated.platform)
        assert isinstance(adapter, adapter_cls)
        assert adapter.can_handle(validated.normalized)

    def test_unknown_domain_raises_invalid_url(self):
        with pytest.raises(InvalidUrlError):
            detect_platform("https://example.com/video/1", check_dns=False)

    def test_unregistered_platform_raises_unsupported(self):
        with pytest.raises(UnsupportedPlatformError):
            get_adapter("facebook")


def test_supported_platforms_lists_all_four():
    assert supported_platforms() == ["instagram", "pinterest", "tiktok", "youtube"]
