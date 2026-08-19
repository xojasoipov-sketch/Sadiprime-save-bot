from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from bot.keyboards.settings import quality_keyboard
from core.config import QualityMode, Settings
from messages.registry import t

router = Router(name="settings")


def _quality_prefs_key(user_id: int) -> str:
    return f"md:prefs:{user_id}:quality"


def _audio_only_prefs_key(user_id: int) -> str:
    return f"md:prefs:{user_id}:audio_only"


async def get_user_quality(redis: Redis, user_id: int, default: QualityMode) -> QualityMode:
    raw = await redis.get(_quality_prefs_key(user_id))
    if raw and raw in QualityMode.__members__:
        return QualityMode[raw]
    return default


async def get_user_audio_only(redis: Redis, user_id: int) -> bool:
    raw = await redis.get(_audio_only_prefs_key(user_id))
    return raw == "1"


@router.message(Command("settings"))
async def handle_settings(message: Message, settings: Settings, redis: Redis) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    current = await get_user_quality(redis, user_id, settings.default_quality)
    audio_only = await get_user_audio_only(redis, user_id)
    await message.answer(
        t(settings.default_language.value, "settings_title"),
        reply_markup=quality_keyboard(
            current, audio_only=audio_only, lang=settings.default_language.value
        ),
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
    await redis.set(_quality_prefs_key(callback.from_user.id), quality.value, ex=180 * 86400)
    audio_only = await get_user_audio_only(redis, callback.from_user.id)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=quality_keyboard(
                quality, audio_only=audio_only, lang=settings.default_language.value
            )
        )
    await callback.answer(
        t(settings.default_language.value, "settings_saved", quality=quality.value)
    )


@router.callback_query(lambda c: c.data == "audio_only:toggle")
async def handle_audio_only_toggle(
    callback: CallbackQuery, settings: Settings, redis: Redis
) -> None:
    user_id = callback.from_user.id
    new_value = not await get_user_audio_only(redis, user_id)
    await redis.set(_audio_only_prefs_key(user_id), "1" if new_value else "0", ex=180 * 86400)

    quality = await get_user_quality(redis, user_id, settings.default_quality)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=quality_keyboard(
                quality, audio_only=new_value, lang=settings.default_language.value
            )
        )
    key = "settings_audio_only_on" if new_value else "settings_audio_only_off"
    await callback.answer(t(settings.default_language.value, key))
