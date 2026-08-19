"""Short-lived Redis storage for "pick one of these search results" state.

A results list is too big to fit in a Telegram callback_data (64 bytes),
so we store it server-side under a short session id and only put
`musicpick:<session_id>:<index>` in the button. Sessions expire quickly —
this is a UI convenience, not durable state.
"""

from __future__ import annotations

import json
import uuid

from redis.asyncio import Redis

from downloader.music_search import SearchCandidate

_SESSION_TTL_SECONDS = 300


def _session_key(session_id: str) -> str:
    return f"md:searchsession:{session_id}"


async def create_session(redis: Redis, *, user_id: int, candidates: list[SearchCandidate]) -> str:
    session_id = uuid.uuid4().hex[:12]
    payload = {
        "user_id": user_id,
        "candidates": [
            {"url": c.url, "title": c.title, "duration_seconds": c.duration_seconds}
            for c in candidates
        ],
    }
    await redis.set(_session_key(session_id), json.dumps(payload), ex=_SESSION_TTL_SECONDS)
    return session_id


async def get_candidate(
    redis: Redis, *, session_id: str, index: int, requester_id: int
) -> SearchCandidate | None:
    """Return the candidate at `index`, or None if the session is gone/expired,
    the index is out of range, or `requester_id` doesn't match who searched."""

    raw = await redis.get(_session_key(session_id))
    if not raw:
        return None

    payload = json.loads(raw)
    if payload.get("user_id") != requester_id:
        return None

    candidates = payload.get("candidates") or []
    if not (0 <= index < len(candidates)):
        return None

    entry = candidates[index]
    return SearchCandidate(
        url=entry["url"], title=entry["title"], duration_seconds=entry.get("duration_seconds")
    )
