from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from core.config import Settings
from messages.registry import t

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message, settings: Settings) -> None:
    await message.answer(t(settings.default_language.value, "start"))
