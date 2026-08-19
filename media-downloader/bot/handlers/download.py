"""Primary user flow: receive a URL, validate it, enqueue a job.

The actual download/upload work happens in the worker process — this
handler's only job is to validate input fast, apply per-user limits, and
hand off a job id. Section 6 UX: immediate "🔎 Link detected" feedback.
"""

from __future__ import annotations

import re

from aiogram import Router
from aiogram.types import Message
from redis.asyncio import Redis

from bot.handlers.settings import get_user_quality
from core.config import Settings
from core.limits import Limiter, QueueFullError, RateLimitError
from core.security import InvalidUrlError
from downloader.base import UnsupportedPlatformError
from downloader.registry import detect_platform
from messages.registry import t
from worker.services.job_store import Job, JobStore

router = Router(name="download")

_URL_RE = re.compile(r"https?://\S+")


@router.message()
async def handle_message(message: Message, settings: Settings, redis: Redis) -> None:
    if not message.text or message.from_user is None:
        return

    match = _URL_RE.search(message.text)
    lang = settings.default_language.value
    if not match:
        await message.answer(t(lang, "error_unsupported_link"))
        return

    url = match.group(0)
    user_id = message.from_user.id

    try:
        validated = detect_platform(url)
    except (InvalidUrlError, UnsupportedPlatformError):
        await message.answer(t(lang, "error_unsupported_link"))
        return

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
        await message.answer(t(lang, "error_rate_limited"))
        return
    except QueueFullError:
        await message.answer(t(lang, "error_queue_full"))
        return

    status_message = await message.answer(t(lang, "link_detected"))

    quality = await get_user_quality(redis, user_id, settings.default_quality)
    store = JobStore(redis)
    job = Job(
        job_id=JobStore.new_job_id(),
        user_id=user_id,
        chat_id=message.chat.id,
        url=validated.normalized,
        platform=validated.platform,
        quality=quality.value,
        status_message_id=status_message.message_id,
    )

    await store.create(job)
    await limiter.increment_daily_quota(user_id)
    await limiter.register_active_job(user_id, job.job_id)
