"""Job model + Redis-backed persistence.

Redis is the only datastore (section 28: no Postgres/SQLite unless truly
necessary). A job is a Redis hash `md:job:<job_id>` plus a lease key used
for crash recovery (section 25).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum

from redis.asyncio import Redis


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    PROCESSING = "PROCESSING"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class Job:
    job_id: str
    user_id: int
    chat_id: int
    url: str
    platform: str
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    quality: str = "BEST_COMPATIBLE"
    attempt: int = 0
    status_message_id: int | None = None
    audio_only: bool = False

    def to_json(self) -> str:
        d = asdict(self)
        d["status"] = self.status.value
        return json.dumps(d)

    @classmethod
    def from_json(cls, raw: str) -> Job:
        d = json.loads(raw)
        d["status"] = JobStatus(d["status"])
        return cls(**d)


_JOB_KEY_PREFIX = "md:job:"
_LEASE_KEY_PREFIX = "md:lease:"
_QUEUE_KEY = "md:queue:pending"
_STATS_PREFIX = "md:stats:"


class JobStore:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _job_key(self, job_id: str) -> str:
        return f"{_JOB_KEY_PREFIX}{job_id}"

    def _lease_key(self, job_id: str) -> str:
        return f"{_LEASE_KEY_PREFIX}{job_id}"

    @staticmethod
    def new_job_id() -> str:
        return uuid.uuid4().hex

    async def create(self, job: Job) -> None:
        await self.redis.set(self._job_key(job.job_id), job.to_json(), ex=86400)
        await self.redis.rpush(_QUEUE_KEY, job.job_id)  # type: ignore[misc]

    async def get(self, job_id: str) -> Job | None:
        raw = await self.redis.get(self._job_key(job_id))
        return Job.from_json(raw) if raw else None

    async def save(self, job: Job) -> None:
        await self.redis.set(self._job_key(job.job_id), job.to_json(), ex=86400)

    async def dequeue(self, timeout_seconds: int = 5) -> str | None:
        """Blocking pop of the next queued job id, or None on timeout."""

        # redis-py's shared sync/async stubs type single commands as
        # `Awaitable[T] | T`; at runtime redis.asyncio always returns an
        # awaitable. See https://github.com/redis/redis-py/issues/2399
        result = await self.redis.blpop([_QUEUE_KEY], timeout=timeout_seconds)  # type: ignore[misc]
        if result is None:
            return None
        _key, job_id = result
        return job_id

    async def queue_size(self) -> int:
        return int(await self.redis.llen(_QUEUE_KEY) or 0)  # type: ignore[misc]

    # --- Lease / heartbeat (crash recovery, section 25) -------------------

    async def acquire_lease(self, job_id: str, ttl_seconds: int) -> None:
        await self.redis.set(self._lease_key(job_id), "1", ex=ttl_seconds)

    async def renew_lease(self, job_id: str, ttl_seconds: int) -> None:
        await self.redis.expire(self._lease_key(job_id), ttl_seconds)

    async def release_lease(self, job_id: str) -> None:
        await self.redis.delete(self._lease_key(job_id))

    async def lease_alive(self, job_id: str) -> bool:
        return bool(await self.redis.exists(self._lease_key(job_id)))

    async def scan_stale_jobs(self) -> list[Job]:
        """Find jobs stuck in an in-progress state with no live lease.

        Used by the periodic worker recovery sweep.
        """

        stale: list[Job] = []
        in_progress = {JobStatus.DOWNLOADING, JobStatus.PROCESSING, JobStatus.UPLOADING}
        async for key in self.redis.scan_iter(match=f"{_JOB_KEY_PREFIX}*"):
            raw = await self.redis.get(key)
            if not raw:
                continue
            job = Job.from_json(raw)
            if job.status in in_progress and not await self.lease_alive(job.job_id):
                stale.append(job)
        return stale

    # --- Stats (section 21/22, plain Redis counters — no DB needed) -----

    async def record_completion(self, platform: str, *, success: bool) -> None:
        pipe = self.redis.pipeline()
        pipe.incr(f"{_STATS_PREFIX}total")
        pipe.incr(f"{_STATS_PREFIX}{'success' if success else 'failure'}")
        pipe.incr(f"{_STATS_PREFIX}platform:{platform}")
        await pipe.execute()

    async def get_stats(self) -> dict[str, int]:
        keys = ["total", "success", "failure"]
        values = await self.redis.mget([f"{_STATS_PREFIX}{k}" for k in keys])
        return {k: int(v or 0) for k, v in zip(keys, values, strict=True)}

    async def get_platform_stats(self) -> dict[str, int]:
        """Per-platform job counts (success + failure combined), for /stats."""

        result: dict[str, int] = {}
        prefix = f"{_STATS_PREFIX}platform:"
        async for key in self.redis.scan_iter(match=f"{prefix}*"):
            platform = key[len(prefix) :]
            value = await self.redis.get(key)
            result[platform] = int(value or 0)
        return result
