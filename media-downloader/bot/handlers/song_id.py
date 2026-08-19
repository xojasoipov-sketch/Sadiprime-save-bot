"""Handles a tap on the "download the song" button attached under a
downloaded video (worker/tasks/download.py:_song_id_keyboard). Fetches the
audio snippet the worker stashed in Redis right after upload, identifies
it via AudD.io, then feeds "artist title" into the same YouTube search +
numbered pick-list used for a plain-text music search
(bot/handlers/download.py / bot/keyboards/music_results.py) — so tapping
the button ends in the same familiar "pick one of 10, get the mp3" flow,
not just a text answer.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis

from bot.keyboards.music_results import format_results_text, results_keyboard
from bot.services.search_sessions import create_session
from bot.services.song_id import SongIdError, get_snippet, identify_song
from core.config import Settings
from downloader.base import DownloaderError
from downloader.music_search import InvalidSearchQueryError, search_candidates
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

    await callback.answer()

    if isinstance(callback.message, Message):
        status_message = await callback.message.answer(t(lang, "song_id_searching"))
    elif callback.from_user is not None:
        status_message = await callback.bot.send_message(  # type: ignore[union-attr]
            callback.from_user.id, t(lang, "song_id_searching")
        )
    else:
        return

    try:
        match = await identify_song(snippet, api_token=settings.audd_api_token)
    except SongIdError:
        await status_message.edit_text(t(lang, "song_id_error"))
        return

    if match is None:
        await status_message.edit_text(t(lang, "song_id_not_found"))
        return

    query = f"{match.artist} {match.title}".strip()
    try:
        candidates = await search_candidates(query)
    except (InvalidSearchQueryError, DownloaderError):
        candidates = []

    if not candidates:
        # Still useful even without a downloadable pick-list.
        text = t(lang, "song_id_result", artist=match.artist, title=match.title)
        if match.song_link:
            text += f"\n{match.song_link}"
        await status_message.edit_text(text)
        return

    if callback.from_user is None:
        return
    session_id = await create_session(redis, user_id=callback.from_user.id, candidates=candidates)
    await status_message.edit_text(
        format_results_text(query, candidates),
        reply_markup=results_keyboard(session_id, len(candidates)),
    )
