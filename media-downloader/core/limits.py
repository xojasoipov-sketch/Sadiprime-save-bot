"""Redis-backed rate limiting and per-user concurrency/quota tracking.

Kept deliberately simple: fixed-window counters for rate limiting, plain
counters for daily quotas, and a Redis set for "currently active jobs per
user". All operations are atomic pipelines so concurrent bot/worker
processes never race each other.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis


class RateLimitError(Exception):
    """Raised when a user exceeds a configured rate/quota limit."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class QueueFullError(Exception):
    """Raised when the global job queue is at capacity."""


@dataclass
class Limiter:
    redis: Redis
    max_requests_per_minute: int
    max_active_jobs_per_user: int
    max_daily_jobs_per_user: int
    max_queue_size: int

    def _minute_key(self, user_id: int) -> str:
        window = int(time.time() // 60)
        return f"md:ratelimit:{user_id}:{window}"

    def _daily_key(self, user_id: int) -> str:
        day = time.strftime("%Y%m%d", time.gmtime())
        return f"md:daily:{user_id}:{day}"

    def _active_key(self, user_id: int) -> str:
        return f"md:active:{user_id}"

    def _queue_key(self) -> str:
        return "md:queue:pending"

    async def check_and_increment_rate(self, user_id: int) -> None:
        key = self._minute_key(user_id)
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 90)
        count, _ = await pipe.execute()
        if count > self.max_requests_per_minute:
            raise RateLimitError(
                "Too many requests per minute", retry_after_seconds=60
            )

    async def check_daily_quota(self, user_id: int) -> None:
        key = self._daily_key(user_id)
        count = await self.redis.get(key)
        if count is not None and int(count) >= self.max_daily_jobs_per_user:
            raise RateLimitError("Daily job quota exceeded", retry_after_seconds=None)

    async def increment_daily_quota(self, user_id: int) -> None:
        key = self._daily_key(user_id)
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 172800)  # 2 days, plenty of margin over UTC day rollover
        await pipe.execute()

    async def active_job_count(self, user_id: int) -> int:
        # redis-py's shared sync/async stubs type single commands as
        # `Awaitable[T] | T`; at runtime redis.asyncio always returns an
        # awaitable. See https://github.com/redis/redis-py/issues/2399
        return int(await self.redis.scard(self._active_key(user_id)) or 0)  # type: ignore[misc]

    async def check_active_limit(self, user_id: int) -> None:
        active = await self.active_job_count(user_id)
        if active >= self.max_active_jobs_per_user:
            raise RateLimitError(
                "You already have a download in progress. Please wait for it to finish.",
                retry_after_seconds=None,
            )

    async def register_active_job(self, user_id: int, job_id: str) -> None:
        key = self._active_key(user_id)
        pipe = self.redis.pipeline()
        pipe.sadd(key, job_id)
        pipe.expire(key, 3600)
        await pipe.execute()

    async def release_active_job(self, user_id: int, job_id: str) -> None:
        await self.redis.srem(self._active_key(user_id), job_id)  # type: ignore[misc]

    async def check_queue_capacity(self) -> None:
        size = await self.redis.llen(self._queue_key())  # type: ignore[misc]
        if size >= self.max_queue_size:
            raise QueueFullError("The download queue is full, please try again later.")
