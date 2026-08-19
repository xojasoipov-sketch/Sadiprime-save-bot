from __future__ import annotations

from pathlib import Path

from core.config import Language, QualityMode, Settings


def test_default_language_is_uzbek():
    settings = Settings()
    assert settings.default_language == Language.UZ


def test_default_quality_is_best_compatible():
    settings = Settings()
    assert settings.default_quality == QualityMode.BEST_COMPATIBLE


def test_admin_user_ids_parses_comma_separated(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", "111, 222 ,333")
    settings = Settings()
    assert settings.admin_user_ids == {111, 222, 333}
    assert settings.is_admin(222)
    assert not settings.is_admin(999)


def test_admin_user_ids_ignores_garbage(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", "abc,,123")
    settings = Settings()
    assert settings.admin_user_ids == {123}


def test_limits_have_sane_defaults():
    settings = Settings()
    assert settings.max_concurrent_downloads >= 1
    assert settings.max_file_size_mb > 0
    assert settings.download_timeout_seconds > 0
    assert settings.job_timeout_seconds >= settings.download_timeout_seconds - 1


def test_cookies_file_is_unset_by_default():
    settings = Settings()
    assert settings.cookies_file is None


def test_cookies_file_parses_env_var_as_path(monkeypatch):
    monkeypatch.setenv("COOKIES_FILE", "/app/secrets/cookies.txt")
    settings = Settings()
    assert settings.cookies_file == Path("/app/secrets/cookies.txt")


def test_force_ipv4_disabled_by_default():
    settings = Settings()
    assert settings.force_ipv4 is False


def test_enable_compression_fallback_on_by_default():
    settings = Settings()
    assert settings.enable_compression_fallback is True
