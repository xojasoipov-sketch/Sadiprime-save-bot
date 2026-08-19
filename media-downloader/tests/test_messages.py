from __future__ import annotations

from messages import en, uz
from messages.registry import t


def test_uz_and_en_have_identical_keys():
    assert set(uz.MESSAGES.keys()) == set(en.MESSAGES.keys())


def test_default_language_is_uzbek_and_populated():
    assert t("uz", "start") == uz.MESSAGES["start"]


def test_unknown_language_falls_back_to_uzbek():
    assert t("fr", "start") == uz.MESSAGES["start"]


def test_unknown_key_returns_key_itself():
    assert t("uz", "no_such_key") == "no_such_key"


def test_formats_placeholders():
    result = t("en", "settings_saved", quality="HIGH")
    assert "HIGH" in result


def test_missing_placeholder_does_not_raise():
    # settings_saved expects `quality`; omitting it must degrade gracefully
    # rather than crash the bot.
    result = t("en", "settings_saved")
    assert result  # returns the raw template rather than raising
