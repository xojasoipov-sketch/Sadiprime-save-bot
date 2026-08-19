"""Handles a tap on one of the numbered search-result buttons.

Turns the chosen SearchCandidate into an actual download job (forced
audio-only), reusing the same limiter/job-creation path as a direct URL
(bot/handlers/download.py:enqueue_download_job). The candidate's URL came
from yt-dlp's own search results, not raw user input, but we still run it
through detect_platform() for the same SSRF/domain validation everything
else gets — defense in depth, not an assumption that yt-dlp is infallible.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from bot.handlers.download import enqueue_download_job
from bot.services.search_sessions import get_candidate
from core.config import Settings
from core.security import InvalidUrlError
from downloader.base import UnsupportedPlatformError
from downloader.registry import detect_platform
from messages.registry import t

router = Router(name="music_pick")


@router.callback_query(lambda c: c.data and c.data.startswith("musicpick:"))
async def handle_music_pick(callback: CallbackQuery, settings: Settings, redis: Redis) -> None:
    lang = settings.default_language.value

    if not callback.data or callback.from_user is None:
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, session_id, index_raw = parts
    if not index_raw.isdigit():
        await callback.answer()
        return

    candidate = await get_candidate(
        redis, session_id=session_id, index=int(index_raw), requester_id=callback.from_user.id
    )
    if candidate is None:
        await callback.answer(t(lang, "error_search_expired"), show_alert=True)
        return

    try:
        # check_dns=False: this URL was constructed from yt-dlp's own
        # search response (a video id from youtube.com), not raw user
        # input — the DNS-rebinding check exists to catch an adversarial
        # URL string, which doesn't apply here. Scheme/domain allowlist
        # checks still run.
        validated = detect_platform(candidate.url, check_dns=False)
    except (InvalidUrlError, UnsupportedPlatformError):
        await callback.answer(t(lang, "error_download_failed"), show_alert=True)
        return

    await callback.answer()

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            t(lang, "search_picked", title=candidate.title), reply_markup=None
        )
        answer_target: Message = callback.message
    else:
        # Fallback: original message is gone/inaccessible; still proceed,
        # the new status message below is what the user actually sees.
        answer_target = await callback.bot.send_message(  # type: ignore[union-attr]
            callback.from_user.id, t(lang, "search_picked", title=candidate.title)
        )

    await enqueue_download_job(
        answer_target=answer_target,
        user_id=callback.from_user.id,
        chat_id=answer_target.chat.id,
        settings=settings,
        redis=redis,
        url=validated.normalized,
        platform=validated.platform,
        audio_only=True,
        detected_message_key="downloading",
    )
