"""Message layer — no user-facing string should be hardcoded elsewhere.

Add a new language by dropping a `messages/<code>.py` module exporting a
`MESSAGES: dict[str, str]` with the same keys as `uz.py`, then registering
it in `_CATALOGS` below.
"""

from __future__ import annotations

from messages import en, uz

_CATALOGS: dict[str, dict[str, str]] = {
    "uz": uz.MESSAGES,
    "en": en.MESSAGES,
}

_DEFAULT_LANG = "uz"


def t(lang: str, key: str, **kwargs: object) -> str:
    catalog = _CATALOGS.get(lang, _CATALOGS[_DEFAULT_LANG])
    template = catalog.get(key) or _CATALOGS[_DEFAULT_LANG].get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
