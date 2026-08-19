"""Attach structured-logging context (user_id, chat_id, update_id) to every update."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = structlog.get_logger(component="bot.update")


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update: Update | None = event if isinstance(event, Update) else data.get("event_update")
        user = data.get("event_from_user")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            update_id=getattr(update, "update_id", None),
            user_id=getattr(user, "id", None),
        )
        logger.info("update_received")
        try:
            return await handler(event, data)
        finally:
            structlog.contextvars.clear_contextvars()
