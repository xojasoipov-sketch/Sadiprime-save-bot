from __future__ import annotations

from bot.keyboards.music_results import format_results_text, results_keyboard
from downloader.music_search import SearchCandidate


def make_candidates(n: int) -> list[SearchCandidate]:
    return [
        SearchCandidate(url=f"https://www.youtube.com/watch?v={i}", title=f"Song {i}", duration_seconds=60 + i)
        for i in range(n)
    ]


class TestFormatResultsText:
    def test_numbers_each_result(self):
        text = format_results_text("test query", make_candidates(3))
        assert "1. Song 0" in text
        assert "2. Song 1" in text
        assert "3. Song 2" in text

    def test_includes_query_in_header(self):
        text = format_results_text("Ummon", make_candidates(1))
        assert "Ummon" in text

    def test_truncates_long_titles(self):
        long_title = "x" * 200
        candidates = [SearchCandidate(url="u", title=long_title, duration_seconds=60)]
        text = format_results_text("q", candidates)
        # one of the lines should be truncated with an ellipsis, not the raw 200 chars
        assert long_title not in text
        assert "…" in text


class TestResultsKeyboard:
    def test_creates_one_button_per_candidate(self):
        keyboard = results_keyboard("sess123", 7)
        total_buttons = sum(len(row) for row in keyboard.inline_keyboard)
        assert total_buttons == 7

    def test_buttons_reference_session_and_index(self):
        keyboard = results_keyboard("sess123", 2)
        callback_data = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
        assert callback_data == ["musicpick:sess123:0", "musicpick:sess123:1"]

    def test_wraps_into_rows_of_five(self):
        keyboard = results_keyboard("sess", 10)
        assert [len(row) for row in keyboard.inline_keyboard] == [5, 5]

    def test_partial_last_row(self):
        keyboard = results_keyboard("sess", 7)
        assert [len(row) for row in keyboard.inline_keyboard] == [5, 2]
