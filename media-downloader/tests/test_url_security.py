from __future__ import annotations

import pytest

from core.security import InvalidUrlError, normalize_and_validate_url, sanitize_filename


class TestSchemeValidation:
    def test_rejects_ftp(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("ftp://instagram.com/reel/x", check_dns=False)

    def test_rejects_file_scheme(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("file:///etc/passwd", check_dns=False)

    def test_rejects_no_scheme(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("instagram.com/reel/x", check_dns=False)

    def test_accepts_https(self):
        result = normalize_and_validate_url(
            "https://www.instagram.com/reel/abc123/", check_dns=False
        )
        assert result.platform == "instagram"


class TestSSRFProtection:
    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/reel/x",
            "http://127.0.0.1/reel/x",
            "http://0.0.0.0/reel/x",
            "http://169.254.169.254/latest/meta-data",  # cloud metadata endpoint
            "http://10.0.0.5/reel/x",
            "http://192.168.1.1/reel/x",
            "http://[::1]/reel/x",
        ],
    )
    def test_rejects_private_and_loopback_hosts(self, url):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url(url, check_dns=False)

    def test_rejects_literal_public_ip(self):
        # Even a *public* literal IP is rejected — only named platform
        # domains are allowed.
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("http://8.8.8.8/reel/x", check_dns=False)


class TestDomainAllowlist:
    def test_rejects_unknown_domain(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("https://evil.example.com/x", check_dns=False)

    def test_rejects_lookalike_domain(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("https://instagram.com.evil.com/x", check_dns=False)

    @pytest.mark.parametrize(
        ("url", "platform"),
        [
            ("https://www.instagram.com/reel/x/", "instagram"),
            ("https://instagram.com/p/x/", "instagram"),
            ("https://www.tiktok.com/@user/video/123", "tiktok"),
            ("https://vm.tiktok.com/abc/", "tiktok"),
            ("https://www.youtube.com/watch?v=abc", "youtube"),
            ("https://youtu.be/abc", "youtube"),
            ("https://www.youtube.com/shorts/abc", "youtube"),
            ("https://www.pinterest.com/pin/123/", "pinterest"),
            ("https://pin.it/abc", "pinterest"),
        ],
    )
    def test_accepts_supported_platform_domains(self, url, platform):
        result = normalize_and_validate_url(url, check_dns=False)
        assert result.platform == platform


class TestMalformedUrls:
    def test_rejects_empty(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("", check_dns=False)

    def test_rejects_too_long(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("https://instagram.com/" + "a" * 3000, check_dns=False)

    def test_rejects_no_hostname(self):
        with pytest.raises(InvalidUrlError):
            normalize_and_validate_url("https:///reel/x", check_dns=False)


class TestNormalization:
    def test_forces_https_and_strips_fragment(self):
        result = normalize_and_validate_url(
            "http://www.instagram.com/reel/x/#igsh=abc", check_dns=False
        )
        assert result.normalized.startswith("https://")
        assert "#" not in result.normalized


class TestFilenameSanitization:
    def test_strips_path_traversal(self):
        assert ".." not in sanitize_filename("../../etc/passwd")

    def test_strips_separators(self):
        assert "/" not in sanitize_filename("a/b\\c")

    def test_empty_input_yields_safe_default(self):
        assert sanitize_filename("") == "file"

    def test_truncates_long_names(self):
        assert len(sanitize_filename("a" * 500)) <= 150
