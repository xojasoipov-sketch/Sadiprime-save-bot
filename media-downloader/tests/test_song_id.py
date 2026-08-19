"""Tests for bot/services/song_id.py.

Response parsing is tested directly (pure function, no network — mirrors
downloader/music_search.py's _parse_search_entries tests). The network
call itself is exercised with a fake aiohttp session so the suite never
touches the real AudD.io API.
"""

from __future__ import annotations

import aiohttp
import pytest

from bot.services.song_id import (
    SongIdError,
    SongMatch,
    _parse_audd_response,
    discard_snippet,
    get_snippet,
    identify_song,
    store_snippet,
)


class TestParseAuddResponse:
    def test_successful_match_returns_song_match(self):
        payload = {
            "status": "success",
            "result": {
                "artist": "Test Artist",
                "title": "Test Title",
                "album": "Test Album",
                "song_link": "https://lis.tn/abc",
            },
        }
        match = _parse_audd_response(payload)
        assert match == SongMatch(
            artist="Test Artist",
            title="Test Title",
            album="Test Album",
            song_link="https://lis.tn/abc",
        )

    def test_no_match_returns_none(self):
        payload = {"status": "success", "result": None}
        assert _parse_audd_response(payload) is None

    def test_falls_back_to_spotify_link_when_song_link_missing(self):
        payload = {
            "status": "success",
            "result": {
                "artist": "A",
                "title": "T",
                "spotify": {"external_urls": {"spotify": "https://open.spotify.com/track/x"}},
            },
        }
        match = _parse_audd_response(payload)
        assert match.song_link == "https://open.spotify.com/track/x"

    def test_falls_back_to_apple_music_link(self):
        payload = {
            "status": "success",
            "result": {
                "artist": "A",
                "title": "T",
                "apple_music": {"url": "https://music.apple.com/x"},
            },
        }
        match = _parse_audd_response(payload)
        assert match.song_link == "https://music.apple.com/x"

    def test_no_link_available_is_none(self):
        payload = {"status": "success", "result": {"artist": "A", "title": "T"}}
        match = _parse_audd_response(payload)
        assert match.song_link is None

    def test_error_status_raises_song_id_error(self):
        payload = {"status": "error", "error": {"error_message": "invalid token"}}
        with pytest.raises(SongIdError, match="invalid token"):
            _parse_audd_response(payload)


class TestSnippetRedisRoundtrip:
    async def test_store_then_get_returns_same_bytes(self, fake_redis):
        await store_snippet(fake_redis, job_id="job1", audio_bytes=b"\x00\x01\x02mp3data")
        result = await get_snippet(fake_redis, job_id="job1")
        assert result == b"\x00\x01\x02mp3data"

    async def test_get_missing_snippet_returns_none(self, fake_redis):
        assert await get_snippet(fake_redis, job_id="does-not-exist") is None

    async def test_discard_removes_snippet(self, fake_redis):
        await store_snippet(fake_redis, job_id="job2", audio_bytes=b"bytes")
        await discard_snippet(fake_redis, job_id="job2")
        assert await get_snippet(fake_redis, job_id="job2") is None

    async def test_different_jobs_are_isolated(self, fake_redis):
        await store_snippet(fake_redis, job_id="job-a", audio_bytes=b"aaa")
        await store_snippet(fake_redis, job_id="job-b", audio_bytes=b"bbb")
        assert await get_snippet(fake_redis, job_id="job-a") == b"aaa"
        assert await get_snippet(fake_redis, job_id="job-b") == b"bbb"


class _FakeResponse:
    def __init__(self, *, status: int, payload: dict):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response
        self.posted_to: str | None = None

    def post(self, url, data=None):
        self.posted_to = url
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class TestIdentifySongNetworkCall:
    async def test_success_returns_song_match(self, monkeypatch):
        response = _FakeResponse(
            status=200,
            payload={
                "status": "success",
                "result": {"artist": "Artist", "title": "Title"},
            },
        )
        monkeypatch.setattr(
            aiohttp, "ClientSession", lambda *a, **k: _FakeSession(response)
        )

        match = await identify_song(b"fake audio", api_token="tok")
        assert match == SongMatch(artist="Artist", title="Title", album=None, song_link=None)

    async def test_non_200_status_raises_song_id_error(self, monkeypatch):
        response = _FakeResponse(status=500, payload={})
        monkeypatch.setattr(
            aiohttp, "ClientSession", lambda *a, **k: _FakeSession(response)
        )

        with pytest.raises(SongIdError, match="HTTP 500"):
            await identify_song(b"fake audio", api_token="tok")
