"""Coarse global per-user rate limit applied to every message update.

Download-specific limits (active job slot, daily quota, queue capacity)
are checked separately in bot/handlers/download.py since they only make
sense for URL submissions, not for /start, /help, etc.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from redis.asyncio import Redis

from core.config import Settings
from core.limits import Limiter, RateLimitError
from messages.registry import t


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, settings: Settings):
        self.redis = redis
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)

        limiter = Limiter(
            redis=self.redis,
            max_requests_per_minute=self.settings.max_requests_per_minute,
            max_active_jobs_per_user=self.settings.max_active_jobs_per_user,
            max_daily_jobs_per_user=self.settings.max_daily_jobs_per_user,
            max_queue_size=self.settings.max_queue_size,
        )
        try:
            await limiter.check_and_increment_rate(event.from_user.id)
        except RateLimitError:
            await event.answer(t(self.settings.default_language.value, "error_rate_limited"))
            return None

        return await handler(event, data)
