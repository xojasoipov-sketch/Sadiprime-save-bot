"""Integration-style tests for the bot-layer search -> pick -> enqueue flow.

Uses lightweight duck-typed fakes for aiogram's Message/CallbackQuery
(building real ones requires a live Bot context) — the handlers only call
.answer()/.edit_text() and read .from_user/.chat/.text/.data, so that's
all the fakes need to provide. Everything else (Redis, settings) is real
(fakeredis) so the actual limiter/job-store/session-store logic runs.
"""

from __future__ import annotations

import pytest

from bot.handlers.download import enqueue_download_job, handle_message
from bot.handlers.music_pick import handle_music_pick
from bot.services.search_sessions import create_session
from core.config import Settings
from downloader.music_search import SearchCandidate
from worker.services.job_store import JobStore


class FakeChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeSentMessage:
    def __init__(self, message_id: int = 555):
        self.message_id = message_id
        self.edits: list[str] = []
        self.replies: list[str] = []
        self.chat = FakeChat(42)

    async def answer(self, text, **kwargs):
        self.replies.append(text)
        return FakeSentMessage()

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class FakeMessage:
    def __init__(self, text: str, user_id: int = 42, chat_id: int = 42):
        self.text = text
        self.from_user = FakeUser(user_id)
        self.chat = FakeChat(chat_id)
        self.sent: list[str] = []
        self._last_sent: FakeSentMessage | None = None

    async def answer(self, text, **kwargs):
        msg = FakeSentMessage()
        self.sent.append(text)
        self._last_sent = msg
        return msg


class FakeBot:
    """Note: callback.message in these tests is a FakeSentMessage, not a
    real aiogram Message, so handle_music_pick's `isinstance(..., Message)`
    check is always False — it always takes the "message inaccessible"
    fallback branch and sends a fresh message via this fake bot instead of
    editing callback.message in place. That branch is exactly as load-
    bearing as the edit_text one (same enqueue_download_job call
    afterwards), so this still exercises the real business logic."""

    def __init__(self):
        self.sent_messages: list[FakeSentMessage] = []

    async def send_message(self, chat_id, text, **kwargs):
        msg = FakeSentMessage()
        msg.edits.append(text)  # so assertions can find the sent text
        self.sent_messages.append(msg)
        return msg


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int, message: FakeSentMessage):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.message = message
        self.bot = FakeBot()
        self.answers: list[tuple] = []

    async def answer(self, text: str = "", show_alert: bool = False):
        self.answers.append((text, show_alert))


def make_settings() -> Settings:
    return Settings(BOT_TOKEN="test")


@pytest.fixture
def settings():
    return make_settings()


class TestEnqueueDownloadJob:
    async def test_creates_job_with_requested_platform_and_audio_only(
        self, fake_redis, settings
    ):
        target = FakeSentMessage()
        await enqueue_download_job(
            answer_target=target,
            user_id=1,
            chat_id=1,
            settings=settings,
            redis=fake_redis,
            url="https://www.youtube.com/watch?v=abc",
            platform="youtube",
            audio_only=True,
            detected_message_key="downloading",
        )

        store = JobStore(fake_redis)
        assert await store.queue_size() == 1
        job_id = await store.dequeue(timeout_seconds=1)
        job = await store.get(job_id)
        assert job.platform == "youtube"
        assert job.audio_only is True
        assert job.url == "https://www.youtube.com/watch?v=abc"

    async def test_blocks_second_job_while_one_is_active(self, fake_redis, settings):
        from core.limits import Limiter

        limiter = Limiter(
            redis=fake_redis,
            max_requests_per_minute=100,
            max_active_jobs_per_user=1,
            max_daily_jobs_per_user=100,
            max_queue_size=100,
        )
        await limiter.register_active_job(user_id=1, job_id="already-running")

        target = FakeSentMessage()
        await enqueue_download_job(
            answer_target=target,
            user_id=1,
            chat_id=1,
            settings=settings,
            redis=fake_redis,
            url="https://www.youtube.com/watch?v=abc",
            platform="youtube",
            audio_only=False,
            detected_message_key="downloading",
        )

        store = JobStore(fake_redis)
        assert await store.queue_size() == 0  # rejected, not enqueued
        assert any("⏳" in msg for msg in target.replies)


class TestSearchBranch:
    async def test_plain_text_triggers_search_and_shows_results(
        self, fake_redis, settings, monkeypatch
    ):
        candidates = [
            SearchCandidate(url="https://www.youtube.com/watch?v=a", title="Song A", duration_seconds=120),
            SearchCandidate(url="https://www.youtube.com/watch?v=b", title="Song B", duration_seconds=90),
        ]

        async def fake_search(query, **kwargs):
            return candidates

        monkeypatch.setattr(
            "bot.handlers.download.search_candidates", fake_search
        )

        message = FakeMessage("Ummon Yolg'iz")
        await handle_message(message, settings, fake_redis)

        # First answer() is the "searching..." status message; it then gets
        # edited to the results list.
        assert len(message.sent) == 1
        sent_msg = message._last_sent
        assert sent_msg is not None
        assert any("Song A" in text for text in sent_msg.edits)
        assert any("Song B" in text for text in sent_msg.edits)

    async def test_no_results_shows_error(self, fake_redis, settings, monkeypatch):
        async def fake_search(query, **kwargs):
            return []

        monkeypatch.setattr(
            "bot.handlers.download.search_candidates", fake_search
        )

        message = FakeMessage("asdkjaslkdjaslkdj")
        await handle_message(message, settings, fake_redis)

        sent_msg = message._last_sent
        assert any("topilmadi" in text.lower() or "nothing" in text.lower() for text in sent_msg.edits)


class TestMusicPickHandler:
    async def test_pick_enqueues_a_job_for_the_chosen_candidate(
        self, fake_redis, settings
    ):
        candidates = [
            SearchCandidate(url="https://www.youtube.com/watch?v=a", title="Song A", duration_seconds=120),
            SearchCandidate(url="https://www.youtube.com/watch?v=b", title="Song B", duration_seconds=90),
        ]
        session_id = await create_session(fake_redis, user_id=42, candidates=candidates)

        results_message = FakeSentMessage()
        callback = FakeCallbackQuery(
            data=f"musicpick:{session_id}:1", user_id=42, message=results_message
        )

        await handle_music_pick(callback, settings, fake_redis)

        store = JobStore(fake_redis)
        assert await store.queue_size() == 1
        job_id = await store.dequeue(timeout_seconds=1)
        job = await store.get(job_id)
        assert job.url == "https://www.youtube.com/watch?v=b"
        assert job.audio_only is True
        # See FakeBot docstring: with fake (non-aiogram) message objects
        # the handler always takes its "message inaccessible" fallback and
        # confirms via a freshly sent message rather than editing in place.
        all_sent_text = [t for m in callback.bot.sent_messages for t in m.edits]
        assert any("Song B" in text for text in all_sent_text)

    async def test_expired_session_shows_alert_and_enqueues_nothing(
        self, fake_redis, settings
    ):
        results_message = FakeSentMessage()
        callback = FakeCallbackQuery(
            data="musicpick:does-not-exist:0", user_id=42, message=results_message
        )

        await handle_music_pick(callback, settings, fake_redis)

        store = JobStore(fake_redis)
        assert await store.queue_size() == 0
        assert callback.answers and callback.answers[0][1] is True  # show_alert=True

    async def test_wrong_user_cannot_pick_someone_elses_search(self, fake_redis, settings):
        candidates = [
            SearchCandidate(url="https://www.youtube.com/watch?v=a", title="Song A", duration_seconds=120)
        ]
        session_id = await create_session(fake_redis, user_id=42, candidates=candidates)

        results_message = FakeSentMessage()
        callback = FakeCallbackQuery(
            data=f"musicpick:{session_id}:0", user_id=999, message=results_message
        )

        await handle_music_pick(callback, settings, fake_redis)

        store = JobStore(fake_redis)
        assert await store.queue_size() == 0
