from aiogram import Dispatcher

from bot.handlers.download import router as download_router
from bot.handlers.help import router as help_router
from bot.handlers.music_pick import router as music_pick_router
from bot.handlers.settings import router as settings_router
from bot.handlers.song_id import router as song_id_router
from bot.handlers.start import router as start_router
from bot.handlers.stats import router as stats_router
from bot.handlers.status import router as status_router


def register_all_handlers(dp: Dispatcher) -> None:
    dp.include_router(start_router)
    dp.include_router(help_router)
    dp.include_router(settings_router)
    dp.include_router(status_router)
    dp.include_router(stats_router)
    dp.include_router(music_pick_router)
    dp.include_router(song_id_router)
    # download_router's catch-all text handler must be registered last.
    dp.include_router(download_router)
