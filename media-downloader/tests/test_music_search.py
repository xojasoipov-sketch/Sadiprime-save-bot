from __future__ import annotations

import pytest

from downloader.music_search import (
    SEARCH_PLATFORM,
    InvalidSearchQueryError,
    MusicSearchAdapter,
    SearchCandidate,
    _parse_search_entries,
    build_search_url,
    format_duration,
    sanitize_query,
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


class TestSanitizeQuery:
    def test_strips_and_collapses_whitespace(self):
        assert sanitize_query("  hello \n\n world  ") == "hello world"

    @pytest.mark.parametrize("query", ["", "a", "  ", "\x00\x01"])
    def test_rejects_empty_or_too_short(self, query):
        with pytest.raises(InvalidSearchQueryError):
            sanitize_query(query)


class TestParseSearchEntries:
    def test_extracts_candidates_from_entries(self):
        info = {
            "entries": [
                {"id": "abc123", "title": "Song One", "duration": 210},
                {"webpage_url": "https://www.youtube.com/watch?v=xyz", "title": "Song Two"},
            ]
        }
        candidates = _parse_search_entries(info, limit=10)
        assert candidates == [
            SearchCandidate(url="https://www.youtube.com/watch?v=abc123", title="Song One", duration_seconds=210),
            SearchCandidate(url="https://www.youtube.com/watch?v=xyz", title="Song Two", duration_seconds=None),
        ]

    def test_respects_limit(self):
        info = {"entries": [{"id": str(i), "title": f"t{i}"} for i in range(20)]}
        candidates = _parse_search_entries(info, limit=3)
        assert len(candidates) == 3

    def test_skips_entries_with_no_id_or_url(self):
        info = {"entries": [{"title": "No URL"}, {"id": "ok", "title": "Has ID"}]}
        candidates = _parse_search_entries(info, limit=10)
        assert len(candidates) == 1
        assert candidates[0].title == "Has ID"

    def test_skips_none_entries(self):
        info = {"entries": [None, {"id": "ok", "title": "Fine"}]}
        candidates = _parse_search_entries(info, limit=10)
        assert len(candidates) == 1

    def test_none_info_returns_empty_list(self):
        assert _parse_search_entries(None, limit=10) == []

    def test_missing_entries_key_returns_empty_list(self):
        assert _parse_search_entries({}, limit=10) == []


class TestFormatDuration:
    def test_formats_minutes_and_seconds(self):
        assert format_duration(185) == "3:05"

    def test_formats_under_a_minute(self):
        assert format_duration(45) == "0:45"

    @pytest.mark.parametrize("value", [None, 0, -5])
    def test_unknown_duration_shows_placeholder(self, value):
        assert format_duration(value) == "?:??"
