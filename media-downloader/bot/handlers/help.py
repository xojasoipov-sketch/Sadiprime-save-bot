from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.config import Settings
from messages.registry import t

router = Router(name="help")


@router.message(Command("help"))
async def handle_help(message: Message, settings: Settings) -> None:
    await message.answer(t(settings.default_language.value, "help"))
