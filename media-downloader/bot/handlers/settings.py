from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from bot.keyboards.settings import quality_keyboard
from core.config import QualityMode, Settings
from messages.registry import t

router = Router(name="settings")


def _prefs_key(user_id: int) -> str:
    return f"md:prefs:{user_id}:quality"


async def get_user_quality(redis: Redis, user_id: int, default: QualityMode) -> QualityMode:
    raw = await redis.get(_prefs_key(user_id))
    if raw and raw in QualityMode.__members__:
        return QualityMode[raw]
    return default


@router.message(Command("settings"))
async def handle_settings(message: Message, settings: Settings, redis: Redis) -> None:
    if message.from_user is None:
        return
    current = await get_user_quality(redis, message.from_user.id, settings.default_quality)
    await message.answer(
        t(settings.default_language.value, "settings_title"),
        reply_markup=quality_keyboard(current),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("quality:"))
async def handle_quality_choice(
    callback: CallbackQuery, settings: Settings, redis: Redis
) -> None:
    if not callback.data:
        await callback.answer()
        return

    _, _, value = callback.data.partition(":")
    if value not in QualityMode.__members__:
        await callback.answer()
        return

    quality = QualityMode[value]
    await redis.set(_prefs_key(callback.from_user.id), quality.value, ex=180 * 86400)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=quality_keyboard(quality))
    await callback.answer(
        t(settings.default_language.value, "settings_saved", quality=quality.value)
    )
