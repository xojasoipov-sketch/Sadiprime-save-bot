"""Music-by-name search.

Not domain-triggered like the other adapters — invoked directly when a
user sends plain text instead of a URL (see bot/handlers/download.py and
bot/handlers/music_pick.py). Two entry points:

  * `search_candidates()` — lightweight multi-result search (no download)
    used to show the user a numbered list to pick from, mirroring the
    familiar "type a song name, get a list" UX of other music bots.
  * `MusicSearchAdapter` / `build_search_url()` — a single-result
    `ytsearch1:` pseudo-URL an adapter can download directly, kept for
    callers that want a "just grab the best match" flow instead of a list.

Either way the result is always audio (mp3): a name search means "give me
the song", not a video file.
"""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass

import yt_dlp

from downloader._ytdlp_common import YtDlpAdapter
from downloader.base import MediaUnavailableError

SEARCH_PLATFORM = "music_search"

_MAX_QUERY_LENGTH = 150
_MAX_RESULTS = 10


class InvalidSearchQueryError(ValueError):
    pass


def sanitize_query(query: str) -> str:
    """Clean free-text search input.

    Strips control characters and collapses whitespace so the text can't
    smuggle anything yt-dlp interprets specially; length is capped
    independently of any file/path use (this string never touches the
    filesystem — it's only ever passed to yt-dlp's search extractor).
    """

    if not query:
        raise InvalidSearchQueryError("Empty search query")

    cleaned = "".join(ch for ch in query if ch.isprintable())
    cleaned = " ".join(cleaned.split())  # collapse whitespace/newlines

    if len(cleaned) < 2:
        raise InvalidSearchQueryError("Search query too short")

    return cleaned[:_MAX_QUERY_LENGTH]


def build_search_url(query: str) -> str:
    """Sanitize `query` and wrap it as a single-result yt-dlp search "URL".

    yt-dlp splits on the first ':' after the scheme-like prefix, so a
    literal colon in the query is safe here — it stays part of the search
    text, not a second pseudo-URL.
    """

    return f"ytsearch1:{sanitize_query(query)}"


class MusicSearchAdapter(YtDlpAdapter):
    """Downloads the single top match for a `ytsearch:` query directly."""

    name = SEARCH_PLATFORM

    extra_ydl_opts = {"noplaylist": True}

    def can_handle(self, url: str) -> bool:
        return url.startswith("ytsearch")


@dataclass
class SearchCandidate:
    url: str
    title: str
    duration_seconds: float | None


def _parse_search_entries(info: dict | None, limit: int) -> list[SearchCandidate]:
    """Pure parsing step, split out from search_candidates() for testability
    without touching yt-dlp/the network."""

    if not info:
        return []

    entries = [e for e in (info.get("entries") or []) if e]
    candidates: list[SearchCandidate] = []
    for entry in entries[:limit]:
        video_id = entry.get("id")
        url = entry.get("url") or entry.get("webpage_url")
        if not url and video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
        if not url:
            continue
        candidates.append(
            SearchCandidate(
                url=url,
                title=entry.get("title") or "Unknown",
                duration_seconds=entry.get("duration"),
            )
        )
    return candidates


def _run_flat_search(query: str, limit: int) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(f"ytsearch{limit}:{query}", download=False)


async def search_candidates(query: str, *, limit: int = _MAX_RESULTS) -> list[SearchCandidate]:
    """Return up to `limit` lightweight (metadata-only, no download) results
    for `query`. Raises InvalidSearchQueryError for bad input, or
    MediaUnavailableError if the search itself fails."""

    sanitized = sanitize_query(query)
    loop = asyncio.get_running_loop()
    try:
        info = await loop.run_in_executor(
            None, functools.partial(_run_flat_search, sanitized, limit)
        )
    except yt_dlp.utils.DownloadError as exc:
        raise MediaUnavailableError(f"Search failed: {exc}") from exc

    return _parse_search_entries(info, limit)


def format_duration(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return "?:??"
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"
