from __future__ import annotations

import pytest

from downloader.music_search import (
    SEARCH_PLATFORM,
    InvalidSearchQueryError,
    MusicSearchAdapter,
    build_search_url,
)
from downloader.registry import get_adapter, supported_platforms


class TestBuildSearchUrl:
    def test_wraps_query_in_ytsearch_prefix(self):
        assert build_search_url("Ummon Yolg'iz") == "ytsearch1:Ummon Yolg'iz"

    def test_collapses_whitespace_and_newlines(self):
        assert build_search_url("  hello \n\n world  ") == "ytsearch1:hello world"

    def test_strips_non_printable_characters(self):
        result = build_search_url("hello\x00\x01world")
        assert "\x00" not in result
        assert "\x01" not in result

    def test_preserves_colon_in_query_text(self):
        result = build_search_url("Artist: Best Song")
        assert result == "ytsearch1:Artist: Best Song"

    def test_truncates_overly_long_queries(self):
        result = build_search_url("a" * 500)
        assert len(result) <= len("ytsearch1:") + 150

    @pytest.mark.parametrize("query", ["", "a", "  ", "\x00\x01"])
    def test_rejects_empty_or_too_short(self, query):
        with pytest.raises(InvalidSearchQueryError):
            build_search_url(query)


class TestMusicSearchAdapter:
    def test_can_handle_search_urls(self):
        adapter = MusicSearchAdapter()
        assert adapter.can_handle("ytsearch1:some song")

    def test_cannot_handle_normal_urls(self):
        adapter = MusicSearchAdapter()
        assert not adapter.can_handle("https://www.youtube.com/watch?v=abc")

    def test_registered_in_registry(self):
        adapter = get_adapter(SEARCH_PLATFORM)
        assert isinstance(adapter, MusicSearchAdapter)

    def test_not_counted_among_url_detectable_platforms(self):
        # music_search is invoked directly by the bot, never via
        # detect_platform(), so it must not appear in supported_platforms().
        assert SEARCH_PLATFORM not in supported_platforms()
