from __future__ import annotations

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
