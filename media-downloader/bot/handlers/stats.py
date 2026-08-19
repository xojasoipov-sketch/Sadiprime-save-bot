"""Admin-only /stats: totals, success rate, and a per-platform breakdown.

Complements /status (live infra health) with lifetime job statistics —
section 21 of the spec. Same Redis counters JobStore.record_completion()
already writes on every job completion; nothing new is tracked here.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from redis.asyncio import Redis

from core.config import Settings
from messages.registry import t
from worker.services.job_store import JobStore

router = Router(name="stats")


@router.message(Command("stats"))
async def handle_stats(message: Message, settings: Settings, redis: Redis) -> None:
    lang = settings.default_language.value
    if message.from_user is None or not settings.is_admin(message.from_user.id):
        await message.answer(t(lang, "not_admin"))
        return

    store = JobStore(redis)
    stats = await store.get_stats()
    platform_stats = await store.get_platform_stats()

    total = stats.get("total", 0)
    success = stats.get("success", 0)
    failure = stats.get("failure", 0)
    success_rate = (success / total * 100) if total else 0.0

    lines = [
        t(lang, "stats_header"),
        "",
        f"Total jobs: {total}",
        f"Success: {success} ({success_rate:.1f}%)",
        f"Failed: {failure}",
    ]

    if platform_stats:
        lines.append("")
        lines.append(t(lang, "stats_top_platforms"))
        for platform, count in sorted(platform_stats.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {platform}: {count}")

    await message.answer("\n".join(lines))
