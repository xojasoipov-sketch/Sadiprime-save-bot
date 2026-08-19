"""Handles a tap on the "identify song" button attached under a
downloaded video (worker/tasks/download.py:_song_id_keyboard). Fetches the
audio snippet the worker stashed in Redis right after upload and sends it
to AudD.io.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from bot.services.song_id import SongIdError, get_snippet, identify_song
from core.config import Settings
from messages.registry import t

router = Router(name="song_id")


@router.callback_query(lambda c: c.data and c.data.startswith("songid:"))
async def handle_song_id(callback: CallbackQuery, settings: Settings, redis: Redis) -> None:
    lang = settings.default_language.value

    if not callback.data:
        await callback.answer()
        return

    _, _, job_id = callback.data.partition(":")
    if not job_id:
        await callback.answer()
        return

    if not settings.audd_api_token:
        # Defensive only: the button isn't shown at all when unset.
        await callback.answer()
        return

    snippet = await get_snippet(redis, job_id=job_id)
    if snippet is None:
        await callback.answer(t(lang, "song_id_expired"), show_alert=True)
        return

    await callback.answer(t(lang, "song_id_searching"))

    if isinstance(callback.message, Message):
        reply_target: Message = callback.message
    elif callback.from_user is not None:
        reply_target = await callback.bot.send_message(  # type: ignore[union-attr]
            callback.from_user.id, t(lang, "song_id_searching")
        )
    else:
        return

    try:
        match = await identify_song(snippet, api_token=settings.audd_api_token)
    except SongIdError:
        await reply_target.answer(t(lang, "song_id_error"))
        return

    if match is None:
        await reply_target.answer(t(lang, "song_id_not_found"))
        return

    text = t(lang, "song_id_result", artist=match.artist, title=match.title)
    if match.song_link:
        text += f"\n{match.song_link}"
    await reply_target.answer(text)
