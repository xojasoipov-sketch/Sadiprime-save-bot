"""Song identification via AudD.io — entirely optional (see core/config.py
`AUDD_API_TOKEN`). Two independent responsibilities live here:

  * A short-lived Redis snippet store (`store_snippet`/`get_snippet`/
    `discard_snippet`), mirroring the pattern in
    bot/services/search_sessions.py: a base64 audio clip is too big to put
    in a callback_data, so the worker stashes it server-side under the
    job_id right after a successful upload — *before* the job's temp
    directory is deleted — and the callback handler fetches it later when
    the user actually taps the button. TTL-bound, not durable state.
  * `identify_song` — the actual AudD.io API call.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import aiohttp
from redis.asyncio import Redis

_SNIPPET_TTL_SECONDS = 600
_AUDD_ENDPOINT = "https://api.audd.io/"
_REQUEST_TIMEOUT_SECONDS = 20


def _snippet_key(job_id: str) -> str:
    return f"md:songid:{job_id}"


async def store_snippet(redis: Redis, *, job_id: str, audio_bytes: bytes) -> None:
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    await redis.set(_snippet_key(job_id), encoded, ex=_SNIPPET_TTL_SECONDS)


async def get_snippet(redis: Redis, *, job_id: str) -> bytes | None:
    encoded = await redis.get(_snippet_key(job_id))
    if not encoded:
        return None
    return base64.b64decode(encoded)


async def discard_snippet(redis: Redis, *, job_id: str) -> None:
    await redis.delete(_snippet_key(job_id))


@dataclass
class SongMatch:
    artist: str
    title: str
    album: str | None = None
    song_link: str | None = None


class SongIdError(Exception):
    """Raised on a network/API failure — never a "no match found" result,
    which is represented as identify_song() returning None."""


def _parse_audd_response(payload: dict) -> SongMatch | None:
    """Pure parsing of AudD.io's JSON body — kept separate from the
    network call so it's testable without mocking HTTP (mirrors
    downloader/music_search.py's _parse_search_entries)."""

    if payload.get("status") != "success":
        error = payload.get("error") or {}
        raise SongIdError(f"AudD error: {error.get('error_message', 'unknown')}")

    result = payload.get("result")
    if not result:
        return None

    song_link = result.get("song_link")
    apple_music = result.get("apple_music") or {}
    spotify = result.get("spotify") or {}
    if not song_link:
        song_link = spotify.get("external_urls", {}).get("spotify") or apple_music.get("url")

    return SongMatch(
        artist=result.get("artist", "?"),
        title=result.get("title", "?"),
        album=result.get("album"),
        song_link=song_link,
    )


async def identify_song(audio_bytes: bytes, *, api_token: str) -> SongMatch | None:
    """POST the snippet to AudD.io. Returns None if AudD recognized the
    clip but found no match; raises SongIdError on a network/API failure
    so the caller can tell "no match" apart from "couldn't check"."""

    form = aiohttp.FormData()
    form.add_field("api_token", api_token)
    form.add_field("return", "apple_music,spotify")
    form.add_field("file", audio_bytes, filename="snippet.mp3", content_type="audio/mpeg")

    try:
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session, session.post(
            _AUDD_ENDPOINT, data=form
        ) as response:
            if response.status != 200:
                raise SongIdError(f"AudD returned HTTP {response.status}")
            payload = await response.json(content_type=None)
    except SongIdError:
        raise
    except Exception as exc:  # noqa: BLE001 - network/parsing boundary
        # Deliberately broad: aiohttp.ClientTimeout expiring raises
        # asyncio.TimeoutError (builtins.TimeoutError on 3.11+), NOT
        # aiohttp.ClientError, and a malformed body can raise a plain
        # JSONDecodeError — a narrower except here previously let those
        # escape uncaught, leaving the caller's "searching…" status
        # message stuck forever since nothing ever reached the
        # SongIdError handler. Every failure at this boundary must
        # become a typed, user-visible error instead of hanging.
        raise SongIdError(f"AudD request failed: {exc}") from exc

    return _parse_audd_response(payload)
