from __future__ import annotations

import pytest

from core.limits import Limiter, QueueFullError, RateLimitError


def make_limiter(redis, **overrides):
    defaults = {
        "redis": redis,
        "max_requests_per_minute": 3,
        "max_active_jobs_per_user": 1,
        "max_daily_jobs_per_user": 5,
        "max_queue_size": 2,
    }
    defaults.update(overrides)
    return Limiter(**defaults)


class TestPerMinuteRateLimit:
    async def test_allows_up_to_the_limit(self, fake_redis):
        limiter = make_limiter(fake_redis, max_requests_per_minute=3)
        for _ in range(3):
            await limiter.check_and_increment_rate(user_id=1)

    async def test_blocks_over_the_limit(self, fake_redis):
        limiter = make_limiter(fake_redis, max_requests_per_minute=2)
        await limiter.check_and_increment_rate(user_id=1)
        await limiter.check_and_increment_rate(user_id=1)
        with pytest.raises(RateLimitError):
            await limiter.check_and_increment_rate(user_id=1)

    async def test_limits_are_per_user(self, fake_redis):
        limiter = make_limiter(fake_redis, max_requests_per_minute=1)
        await limiter.check_and_increment_rate(user_id=1)
        # A different user is unaffected by user 1's usage.
        await limiter.check_and_increment_rate(user_id=2)


class TestActiveJobLimit:
    async def test_blocks_second_concurrent_job_for_same_user(self, fake_redis):
        limiter = make_limiter(fake_redis, max_active_jobs_per_user=1)
        await limiter.check_active_limit(user_id=1)
        await limiter.register_active_job(user_id=1, job_id="job-a")
        with pytest.raises(RateLimitError):
            await limiter.check_active_limit(user_id=1)

    async def test_releasing_frees_the_slot(self, fake_redis):
        limiter = make_limiter(fake_redis, max_active_jobs_per_user=1)
        await limiter.register_active_job(user_id=1, job_id="job-a")
        await limiter.release_active_job(user_id=1, job_id="job-a")
        await limiter.check_active_limit(user_id=1)  # should not raise


class TestDailyQuota:
    async def test_blocks_after_daily_quota_exhausted(self, fake_redis):
        limiter = make_limiter(fake_redis, max_daily_jobs_per_user=2)
        await limiter.increment_daily_quota(user_id=1)
        await limiter.increment_daily_quota(user_id=1)
        with pytest.raises(RateLimitError):
            await limiter.check_daily_quota(user_id=1)


class TestQueueCapacity:
    async def test_blocks_when_queue_full(self, fake_redis):
        limiter = make_limiter(fake_redis, max_queue_size=1)
        await fake_redis.rpush("md:queue:pending", "job-1")
        with pytest.raises(QueueFullError):
            await limiter.check_queue_capacity()

    async def test_allows_when_queue_has_room(self, fake_redis):
        limiter = make_limiter(fake_redis, max_queue_size=5)
        await fake_redis.rpush("md:queue:pending", "job-1")
        await limiter.check_queue_capacity()  # should not raise
