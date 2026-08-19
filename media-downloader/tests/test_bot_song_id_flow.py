"""Integration-style tests for the "download the song" button flow:
snippet lookup -> AudD.io identification -> YouTube search -> the same
numbered pick-list used by a plain-text music search.

Fakes mirror tests/test_bot_music_flow.py's style (duck-typed
Message/CallbackQuery doubles) rather than sharing them, matching this
suite's existing per-file convention: callback.message is never a real
aiogram Message here, so handle_song_id always takes its "message
inaccessible" fallback and replies via callback.bot.send_message — same
branch tests/test_bot_music_flow.py exercises for handle_music_pick.
"""

from __future__ import annotations

from bot.handlers.song_id import handle_song_id
from bot.services.search_sessions import get_candidate
from bot.services.song_id import SongIdError, SongMatch, store_snippet
from core.config import Settings
from downloader.music_search import SearchCandidate
from messages.registry import t


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeSentMessage:
    async def answer(self, text, **kwargs):
        return FakeSentMessage()

    async def edit_text(self, text, **kwargs):
        pass


class FakeBot:
    def __init__(self):
        self.sent_messages: list[_TrackedMessage] = []

    async def send_message(self, chat_id, text, **kwargs):
        msg = _TrackedMessage(text)
        self.sent_messages.append(msg)
        return msg


class _TrackedMessage:
    """The status message the handler sends via FakeBot.send_message, then
    edits in place — .edits records every text it has ever shown."""

    def __init__(self, initial_text: str):
        self.edits: list[str] = [initial_text]
        self.edit_kwargs: list[dict] = []

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)
        self.edit_kwargs.append(kwargs)


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int, message: FakeSentMessage):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = message
        self.bot = FakeBot()
        self.answers: list[tuple] = []

    async def answer(self, text: str = "", show_alert: bool = False):
        self.answers.append((text, show_alert))


def make_settings(**overrides) -> Settings:
    defaults = {"BOT_TOKEN": "test", "AUDD_API_TOKEN": "test-token"}
    defaults.update(overrides)
    return Settings(**defaults)


class TestSongIdButtonFlow:
    async def test_button_disabled_without_token_is_a_noop(self, fake_redis):
        settings = make_settings(AUDD_API_TOKEN=None)
        callback = FakeCallbackQuery(data="songid:job1", user_id=42, message=FakeSentMessage())

        await handle_song_id(callback, settings, fake_redis)

        assert callback.answers == [("", False)]
        assert callback.bot.sent_messages == []

    async def test_expired_snippet_shows_alert(self, fake_redis):
        settings = make_settings()
        callback = FakeCallbackQuery(
            data="songid:does-not-exist", user_id=42, message=FakeSentMessage()
        )

        await handle_song_id(callback, settings, fake_redis)

        expected = t(settings.default_language.value, "song_id_expired")
        assert callback.answers == [(expected, True)]

    async def test_match_with_search_results_shows_pick_list(self, fake_redis, monkeypatch):
        settings = make_settings()
        await store_snippet(fake_redis, job_id="job1", audio_bytes=b"snippet-bytes")

        async def fake_identify(audio_bytes, *, api_token):
            assert audio_bytes == b"snippet-bytes"
            return SongMatch(artist="Real Artist", title="Real Title")

        candidates = [
            SearchCandidate(
                url="https://www.youtube.com/watch?v=a",
                title="Real Artist - Real Title",
                duration_seconds=200,
            ),
        ]

        async def fake_search(query, **kwargs):
            assert "Real Artist" in query and "Real Title" in query
            return candidates

        monkeypatch.setattr("bot.handlers.song_id.identify_song", fake_identify)
        monkeypatch.setattr("bot.handlers.song_id.search_candidates", fake_search)

        callback = FakeCallbackQuery(data="songid:job1", user_id=42, message=FakeSentMessage())
        await handle_song_id(callback, settings, fake_redis)

        status_message = callback.bot.sent_messages[0]
        assert any("Real Artist - Real Title" in text for text in status_message.edits)

        markup = status_message.edit_kwargs[-1]["reply_markup"]
        button = markup.inline_keyboard[0][0]
        assert button.callback_data.startswith("musicpick:")
        session_id = button.callback_data.split(":")[1]

        picked = await get_candidate(
            fake_redis, session_id=session_id, index=0, requester_id=42
        )
        assert picked is not None
        assert picked.url == candidates[0].url

    async def test_match_without_search_results_falls_back_to_text_reply(
        self, fake_redis, monkeypatch
    ):
        settings = make_settings()
        await store_snippet(fake_redis, job_id="job2", audio_bytes=b"snippet-bytes")

        async def fake_identify(audio_bytes, *, api_token):
            return SongMatch(artist="A", title="T", song_link="https://lis.tn/x")

        async def fake_search(query, **kwargs):
            return []

        monkeypatch.setattr("bot.handlers.song_id.identify_song", fake_identify)
        monkeypatch.setattr("bot.handlers.song_id.search_candidates", fake_search)

        callback = FakeCallbackQuery(data="songid:job2", user_id=42, message=FakeSentMessage())
        await handle_song_id(callback, settings, fake_redis)

        status_message = callback.bot.sent_messages[0]
        expected_text = t(settings.default_language.value, "song_id_result", artist="A", title="T")
        assert status_message.edits[-1] == f"{expected_text}\nhttps://lis.tn/x"

    async def test_no_match_edits_not_found(self, fake_redis, monkeypatch):
        settings = make_settings()
        await store_snippet(fake_redis, job_id="job3", audio_bytes=b"snippet-bytes")

        async def fake_identify(audio_bytes, *, api_token):
            return None

        monkeypatch.setattr("bot.handlers.song_id.identify_song", fake_identify)

        callback = FakeCallbackQuery(data="songid:job3", user_id=42, message=FakeSentMessage())
        await handle_song_id(callback, settings, fake_redis)

        status_message = callback.bot.sent_messages[0]
        assert status_message.edits[-1] == t(settings.default_language.value, "song_id_not_found")

    async def test_identify_error_edits_error_message(self, fake_redis, monkeypatch):
        settings = make_settings()
        await store_snippet(fake_redis, job_id="job4", audio_bytes=b"snippet-bytes")

        async def fake_identify(audio_bytes, *, api_token):
            raise SongIdError("boom")

        monkeypatch.setattr("bot.handlers.song_id.identify_song", fake_identify)

        callback = FakeCallbackQuery(data="songid:job4", user_id=42, message=FakeSentMessage())
        await handle_song_id(callback, settings, fake_redis)

        status_message = callback.bot.sent_messages[0]
        assert status_message.edits[-1] == t(settings.default_language.value, "song_id_error")

    async def test_unanticipated_failure_still_resolves_status_message(
        self, fake_redis, monkeypatch
    ):
        """Regression test: any bug/unexpected exception after the status
        message is sent must still resolve it to an error, never leave it
        stuck on "searching…" forever (the exact live bug this fixes)."""
        settings = make_settings()
        await store_snippet(fake_redis, job_id="job5", audio_bytes=b"snippet-bytes")

        async def fake_identify(audio_bytes, *, api_token):
            return SongMatch(artist="A", title="T")

        async def fake_search(query, **kwargs):
            raise RuntimeError("something nobody anticipated")

        monkeypatch.setattr("bot.handlers.song_id.identify_song", fake_identify)
        monkeypatch.setattr("bot.handlers.song_id.search_candidates", fake_search)

        callback = FakeCallbackQuery(data="songid:job5", user_id=42, message=FakeSentMessage())
        await handle_song_id(callback, settings, fake_redis)

        status_message = callback.bot.sent_messages[0]
        assert status_message.edits[-1] == t(settings.default_language.value, "song_id_error")
