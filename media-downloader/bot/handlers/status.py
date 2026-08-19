import time
from pathlib import Path

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis

from core.config import Settings
from media.cleanup import total_temp_usage_bytes
from media.processor import get_free_disk_bytes
from messages.registry import t
from worker.services.job_store import JobStore

WORKER_HEALTH_FILENAME = "worker.healthy"

router = Router(name="status")


@router.message(Command("status"))
async def handle_status(message: Message, settings: Settings, redis: Redis) -> None:
    if message.from_user is None or not settings.is_admin(message.from_user.id):
        await message.answer(t(settings.default_language.value, "not_admin"))
        return

    store = JobStore(redis)

    try:
        await redis.ping()
        redis_ok = True
    except Exception:  # noqa: BLE001
        redis_ok = False

    worker_ok = _worker_healthy(settings.temp_dir / WORKER_HEALTH_FILENAME)
    queue_size = await store.queue_size()
    stats = await store.get_stats()
    free_disk_mb = get_free_disk_bytes(settings.temp_dir) // (1024 * 1024)
    used_temp_mb = total_temp_usage_bytes(settings.temp_dir) // (1024 * 1024)

    lines = [
        t(settings.default_language.value, "status_header"),
        "",
        "BOT: OK",
        f"REDIS: {'OK' if redis_ok else 'DOWN'}",
        f"WORKER: {'OK' if worker_ok else 'STALE/DOWN'}",
        f"DISK: {'OK' if free_disk_mb > settings.min_free_disk_mb / 1024 else 'LOW'}",
        "",
        f"Queue size: {queue_size}",
        f"Total jobs: {stats.get('total', 0)}",
        f"Completed: {stats.get('success', 0)}",
        f"Failed: {stats.get('failure', 0)}",
        "",
        f"Free disk: {free_disk_mb} MB",
        f"Temp usage: {used_temp_mb} / {settings.max_temp_storage_mb} MB",
    ]
    await message.answer("\n".join(lines))


def _worker_healthy(path: Path, max_age_seconds: int = 30) -> bool:
    if not path.exists():
        return False
    try:
        last = float(path.read_text().strip())
    except (ValueError, OSError):
        return False
    return (time.time() - last) < max_age_seconds
