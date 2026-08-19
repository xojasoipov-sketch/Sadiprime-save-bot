"""Music-by-name search adapter.

Not domain-triggered like the other adapters — invoked directly when a
user sends plain text instead of a URL (see bot/handlers/download.py).
Delegates to yt-dlp's built-in `ytsearchN:` pseudo-URL, which runs a
YouTube search and treats the top result like any other extractable URL.
Always produces audio (mp3): a name search means "give me the song", not
a video file.
"""

from __future__ import annotations

from downloader._ytdlp_common import YtDlpAdapter

SEARCH_PLATFORM = "music_search"

_MAX_QUERY_LENGTH = 150


class MusicSearchAdapter(YtDlpAdapter):
    name = SEARCH_PLATFORM

    extra_ydl_opts = {"noplaylist": True}

    def can_handle(self, url: str) -> bool:
        return url.startswith("ytsearch")


class InvalidSearchQueryError(ValueError):
    pass


def build_search_url(query: str) -> str:
    """Sanitize a free-text query and turn it into a yt-dlp search "URL".

    Strips control characters and collapses whitespace so the text can't
    smuggle anything yt-dlp/ffmpeg would interpret specially; length is
    capped independently of any file/path use (this string never touches
    the filesystem — it's only ever passed to yt-dlp's extractor).
    """

    if not query:
        raise InvalidSearchQueryError("Empty search query")

    cleaned = "".join(ch for ch in query if ch.isprintable())
    cleaned = " ".join(cleaned.split())  # collapse whitespace/newlines

    if len(cleaned) < 2:
        raise InvalidSearchQueryError("Search query too short")

    cleaned = cleaned[:_MAX_QUERY_LENGTH]
    # yt-dlp splits on the first ':' after the scheme-like prefix, so a
    # literal colon in the query is safe here — it stays part of the
    # search text, not a second pseudo-URL.
    return f"ytsearch1:{cleaned}"
