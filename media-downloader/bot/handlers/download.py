"""Primary user flow: receive a URL or a song name, enqueue a job.

The actual download/upload work happens in the worker process — this
handler's only job is to validate input fast, apply per-user limits, and
hand off a job id. Section 6 UX: immediate "🔎 Link detected" feedback.

Two entry points share the same limiter/job-creation plumbing
(`enqueue_download_job`):
  * a message containing a supported platform URL -> normal download job
  * a message that is plain text (no URL) -> a lightweight multi-result
    YouTube search (no download yet); the user picks a result via the
    inline keyboard, handled in bot/handlers/music_pick.py, which is what
    actually calls enqueue_download_job for the chosen track.
"""

from __future__ import annotations

import re

from aiogram import Router
from aiogram.types import Message
from redis.asyncio import Redis

from bot.handlers.settings import get_user_audio_only, get_user_quality
from bot.keyboards.music_results import format_results_text, results_keyboard
from bot.services.search_sessions import create_session
from core.config import Settings
from core.limits import Limiter, QueueFullError, RateLimitError
from core.security import InvalidUrlError
from downloader.base import DownloaderError, UnsupportedPlatformError
from downloader.music_search import InvalidSearchQueryError, search_candidates
from downloader.registry import detect_platform
from messages.registry import t
from worker.services.job_store import Job, JobStore

router = Router(name="download")

_URL_RE = re.compile(r"https?://\S+")


async def enqueue_download_job(
    *,
    answer_target: Message,
    user_id: int,
    chat_id: int,
    settings: Settings,
    redis: Redis,
    url: str,
    platform: str,
    audio_only: bool,
    detected_message_key: str,
) -> None:
    """Apply per-user limits and create a job. Shared by the URL flow and
    the music-search "pick a result" flow (bot/handlers/music_pick.py)."""

    lang = settings.default_language.value
    limiter = Limiter(
        redis=redis,
        max_requests_per_minute=settings.max_requests_per_minute,
        max_active_jobs_per_user=settings.max_active_jobs_per_user,
        max_daily_jobs_per_user=settings.max_daily_jobs_per_user,
        max_queue_size=settings.max_queue_size,
    )

    try:
        # Coarse per-minute rate limit already applied by RateLimitMiddleware.
        await limiter.check_active_limit(user_id)
        await limiter.check_daily_quota(user_id)
        await limiter.check_queue_capacity()
    except RateLimitError:
        await answer_target.answer(t(lang, "error_rate_limited"))
        return
    except QueueFullError:
        await answer_target.answer(t(lang, "error_queue_full"))
        return

    status_message = await answer_target.answer(t(lang, detected_message_key))

    quality = await get_user_quality(redis, user_id, settings.default_quality)
    store = JobStore(redis)
    job = Job(
        job_id=JobStore.new_job_id(),
        user_id=user_id,
        chat_id=chat_id,
        url=url,
        platform=platform,
        quality=quality.value,
        status_message_id=status_message.message_id,
        audio_only=audio_only,
    )

    await store.create(job)
    await limiter.increment_daily_quota(user_id)
    await limiter.register_active_job(user_id, job.job_id)


@router.message()
async def handle_message(message: Message, settings: Settings, redis: Redis) -> None:
    if not message.text or message.from_user is None:
        return

    lang = settings.default_language.value
    text = message.text.strip()

    match = _URL_RE.search(text)
    if match:
        url = match.group(0)
        try:
            validated = detect_platform(url)
        except (InvalidUrlError, UnsupportedPlatformError):
            await message.answer(t(lang, "error_unsupported_link"))
            return

        audio_only = await get_user_audio_only(redis, message.from_user.id)
        await enqueue_download_job(
            answer_target=message,
            user_id=message.from_user.id,
            chat_id=message.chat.id,
            settings=settings,
            redis=redis,
            url=validated.normalized,
            platform=validated.platform,
            audio_only=audio_only,
            detected_message_key="link_detected",
        )
        return

    # No URL and it's a bot command we don't recognize -> don't treat it as
    # a search query.
    if text.startswith("/"):
        await message.answer(t(lang, "error_unsupported_link"))
        return

    # Plain text with no URL -> music search: show a pick-list, don't
    # download yet (that happens in bot/handlers/music_pick.py).
    status_message = await message.answer(t(lang, "music_search_detected"))

    try:
        candidates = await search_candidates(text)
    except InvalidSearchQueryError:
        await status_message.edit_text(t(lang, "error_no_query"))
        return
    except DownloaderError:
        await status_message.edit_text(t(lang, "error_download_failed"))
        return

    if not candidates:
        await status_message.edit_text(t(lang, "error_no_search_results"))
        return

    session_id = await create_session(redis, user_id=message.from_user.id, candidates=candidates)
    await status_message.edit_text(
        format_results_text(text, candidates),
        reply_markup=results_keyboard(session_id, len(candidates)),
    )
