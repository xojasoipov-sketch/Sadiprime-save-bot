"""Bot entrypoint — Telegram long polling (no public port required).

Webhook mode can be added later (see README) without touching handler
code: only this file's startup logic would change.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from bot.handlers import register_all_handlers
from bot.middleware.logging import LoggingMiddleware
from bot.middleware.rate_limit import RateLimitMiddleware
from core.config import get_settings
from core.logging import configure_logging, get_logger
from core.redis_client import create_redis

logger = get_logger(component="bot.main")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    redis = create_redis(settings.redis_url)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()

    # Injected into every handler as keyword arguments (aiogram's dependency
    # injection via the dispatcher's workflow data).
    dp["settings"] = settings
    dp["redis"] = redis

    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware(redis=redis, settings=settings))

    register_all_handlers(dp)

    logger.info("bot_starting", default_language=settings.default_language.value)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
