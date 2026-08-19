from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.config import QualityMode
from messages.registry import t

_LABELS = {
    QualityMode.BEST_COMPATIBLE: "✅ Best compatible",
    QualityMode.HIGH: "🔼 High",
    QualityMode.MEDIUM: "➖ Medium",
    QualityMode.LOW: "🔽 Low",
}


def quality_keyboard(
    current: QualityMode, *, audio_only: bool = False, lang: str = "uz"
) -> InlineKeyboardMarkup:
    rows = []
    for mode in QualityMode:
        prefix = "🔘 " if mode == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{_LABELS[mode]}",
                    callback_data=f"quality:{mode.value}",
                )
            ]
        )

    audio_key = "settings_audio_only_on" if audio_only else "settings_audio_only_off"
    rows.append(
        [InlineKeyboardButton(text=t(lang, audio_key), callback_data="audio_only:toggle")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
