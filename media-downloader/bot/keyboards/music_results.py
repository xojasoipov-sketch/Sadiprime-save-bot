from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from downloader.music_search import SearchCandidate, format_duration

_BUTTONS_PER_ROW = 5


def format_results_text(query: str, candidates: list[SearchCandidate]) -> str:
    lines = [f'🎵 "{query}" uchun natijalar:', ""]
    for i, c in enumerate(candidates, start=1):
        title = c.title if len(c.title) <= 60 else c.title[:57] + "…"
        lines.append(f"{i}. {title} — {format_duration(c.duration_seconds)}")
    return "\n".join(lines)


def results_keyboard(session_id: str, count: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(i + 1), callback_data=f"musicpick:{session_id}:{i}")
        for i in range(count)
    ]
    rows = [
        buttons[i : i + _BUTTONS_PER_ROW] for i in range(0, len(buttons), _BUTTONS_PER_ROW)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
