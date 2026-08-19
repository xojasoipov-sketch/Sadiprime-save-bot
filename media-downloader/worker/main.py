"""Worker entrypoint.

Pulls job ids off the Redis queue, runs up to MAX_CONCURRENT_DOWNLOADS
jobs concurrently, and runs two periodic background sweeps:
  * orphaned temp-directory cleanup (media/cleanup.py)
  * stale/crashed job recovery (worker/services/job_store.py)

A liveness file is touched every loop iteration; the Docker healthcheck
(see Dockerfile) considers the worker unhealthy if it goes stale.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from aiogram import Bot

from core.config import get_settings
from core.limits import Limiter
from core.logging import configure_logging, get_logger
from core.redis_client import create_redis
from media.cleanup import sweep_orphaned_dirs
from worker.services.job_store import JobStatus, JobStore
from worker.tasks.download import process_job

WORKER_HEALTH_FILENAME = "worker.healthy"


async def _recovery_sweep(store: JobStore, log: object) -> None:
    stale_jobs = await store.scan_stale_jobs()
    for job in stale_jobs:
        job.status = JobStatus.FAILED
        job.error = "Worker lost its lease (crash/restart) before completing this job"
        await store.save(job)
        log.warning("stale_job_recovered", job_id=job.job_id)  # type: ignore[attr-defined]


async def _periodic_maintenance(settings, store: JobStore, log: object) -> None:
    while True:
        await asyncio.sleep(settings.orphan_cleanup_interval_seconds)
        try:
            removed = sweep_orphaned_dirs(
                settings.temp_dir, max_age_seconds=settings.orphan_max_age_seconds
            )
            if removed:
                log.info("orphan_sweep_completed", removed=removed)  # type: ignore[attr-defined]
            await _recovery_sweep(store, log)
        except Exception as exc:  # noqa: BLE001
            log.error("maintenance_sweep_failed", error=str(exc))  # type: ignore[attr-defined]


async def _touch_health_file(temp_dir: Path) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    (temp_dir / WORKER_HEALTH_FILENAME).write_text(str(time.time()))


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(component="worker.main")

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    redis = create_redis(settings.redis_url)
    store = JobStore(redis)
    limiter = Limiter(
        redis=redis,
        max_requests_per_minute=settings.max_requests_per_minute,
        max_active_jobs_per_user=settings.max_active_jobs_per_user,
        max_daily_jobs_per_user=settings.max_daily_jobs_per_user,
        max_queue_size=settings.max_queue_size,
    )
    bot = Bot(token=settings.bot_token)

    semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
    maintenance_task = asyncio.create_task(_periodic_maintenance(settings, store, log))

    log.info(
        "worker_started",
        max_concurrent_downloads=settings.max_concurrent_downloads,
        temp_dir=str(settings.temp_dir),
    )

    async def _run_with_semaphore(job_id: str) -> None:
        async with semaphore:
            job = await store.get(job_id)
            if job is None:
                log.warning("job_not_found", job_id=job_id)
                return
            await process_job(job, bot=bot, store=store, limiter=limiter, settings=settings)

    try:
        while True:
            await _touch_health_file(settings.temp_dir)
            job_id = await store.dequeue(timeout_seconds=5)
            if job_id is None:
                continue
            asyncio.create_task(_run_with_semaphore(job_id))
    finally:
        maintenance_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance_task
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
