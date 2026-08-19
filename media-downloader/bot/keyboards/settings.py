from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.config import QualityMode

_LABELS = {
    QualityMode.BEST_COMPATIBLE: "✅ Best compatible",
    QualityMode.HIGH: "🔼 High",
    QualityMode.MEDIUM: "➖ Medium",
    QualityMode.LOW: "🔽 Low",
}


def quality_keyboard(current: QualityMode) -> InlineKeyboardMarkup:
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
    return InlineKeyboardMarkup(inline_keyboard=rows)
