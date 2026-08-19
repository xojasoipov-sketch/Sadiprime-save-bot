"""Integration-style tests for the full job pipeline in worker/tasks/download.py.

Everything external (Telegram, yt-dlp/adapters) is faked so these tests
are deterministic and never touch the network, per section 34/35: the
normal suite must not depend on live platform availability.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import QualityMode, Settings
from core.limits import Limiter
from downloader.base import (
    DownloaderAdapter,
    DownloadOptions,
    DownloadResult,
    MediaFile,
    MediaKind,
    PrivateContentError,
)
from downloader.base import DownloadTimeoutError as AdapterDownloadTimeoutError
from worker.services.job_store import Job, JobStatus, JobStore
from worker.tasks import download as download_task

_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
)


class FakeBot:
    def __init__(self):
        self.edits: list[str] = []
        self.sent: list[str] = []

    async def edit_message_text(self, chat_id, message_id, text):
        self.edits.append(text)

    async def send_photo(self, chat_id, photo, caption=None):
        self.sent.append("photo")

    async def send_video(self, chat_id, video, caption=None):
        self.sent.append("video")

    async def send_audio(self, chat_id, audio, caption=None):
        self.sent.append("audio")

    async def send_media_group(self, chat_id, media):
        self.sent.append(f"group:{len(media)}")


class ScriptedAdapter(DownloaderAdapter):
    """Adapter double that fails N times before succeeding (or never)."""

    name = "instagram"

    def __init__(self, failures: list[Exception]):
        self.failures = list(failures)
        self.call_count = 0

    def can_handle(self, url: str) -> bool:
        return True

    async def get_metadata(self, url: str) -> dict:
        return {}

    async def download(self, url: str, options: DownloadOptions) -> DownloadResult:
        self.call_count += 1
        if self.failures:
            raise self.failures.pop(0)

        options.output_dir.mkdir(parents=True, exist_ok=True)
        file_path = options.output_dir / "media.png"
        file_path.write_bytes(_PNG_BYTES)
        media_file = MediaFile(
            path=file_path,
            kind=MediaKind.IMAGE,
            size_bytes=file_path.stat().st_size,
            width=1,
            height=1,
        )
        return DownloadResult(files=[media_file], source_url=url, platform="instagram")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        BOT_TOKEN="test",
        TEMP_DIR=tmp_path,
        MAX_TEMP_STORAGE_MB=10000,
        JOB_LEASE_SECONDS=30,
        JOB_TIMEOUT_SECONDS=10,
        DOWNLOAD_TIMEOUT_SECONDS=5,
        UPLOAD_TIMEOUT_SECONDS=5,
    )


@pytest.fixture(autouse=True)
def _bypass_real_disk_check(monkeypatch):
    # Disk-capacity checks hit the real filesystem `tmp_path` lives on;
    # keep these tests deterministic regardless of the CI host's free space.
    monkeypatch.setattr(download_task, "check_disk_capacity", lambda *a, **k: None)


def make_job(tmp_path: Path) -> Job:
    return Job(
        job_id=JobStore.new_job_id(),
        user_id=42,
        chat_id=42,
        url="https://www.instagram.com/reel/x/",
        platform="instagram",
        quality=QualityMode.BEST_COMPATIBLE.value,
        status_message_id=1,
    )


@pytest.fixture
def limiter(fake_redis):
    return Limiter(
        redis=fake_redis,
        max_requests_per_minute=10,
        max_active_jobs_per_user=1,
        max_daily_jobs_per_user=50,
        max_queue_size=100,
    )


class TestSuccessPath:
    async def test_job_completes_and_cleans_up(self, fake_redis, limiter, tmp_path, monkeypatch):
        settings = make_settings(tmp_path)
        store = JobStore(fake_redis)
        job = make_job(tmp_path)
        await store.create(job)
        await limiter.register_active_job(job.user_id, job.job_id)

        adapter = ScriptedAdapter(failures=[])
        monkeypatch.setattr(download_task, "get_adapter", lambda platform: adapter)

        bot = FakeBot()
        await download_task.process_job(
            job, bot=bot, store=store, limiter=limiter, settings=settings
        )

        saved = await store.get(job.job_id)
        assert saved.status == JobStatus.COMPLETED
        assert bot.sent == ["photo"]
        assert not (settings.temp_dir / job.job_id).exists()
        assert await limiter.active_job_count(job.user_id) == 0
        assert not await store.lease_alive(job.job_id)

        stats = await store.get_stats()
        assert stats["success"] == 1


class TestRetryBehavior:
    async def test_retryable_error_retries_then_succeeds(
        self, fake_redis, limiter, tmp_path, monkeypatch
    ):
        settings = make_settings(tmp_path)
        store = JobStore(fake_redis)
        job = make_job(tmp_path)
        await store.create(job)

        adapter = ScriptedAdapter(failures=[AdapterDownloadTimeoutError("slow")])
        monkeypatch.setattr(download_task, "get_adapter", lambda platform: adapter)

        bot = FakeBot()
        await download_task.process_job(
            job, bot=bot, store=store, limiter=limiter, settings=settings
        )

        assert adapter.call_count == 2
        saved = await store.get(job.job_id)
        assert saved.status == JobStatus.COMPLETED

    async def test_non_retryable_error_fails_immediately(
        self, fake_redis, limiter, tmp_path, monkeypatch
    ):
        settings = make_settings(tmp_path)
        store = JobStore(fake_redis)
        job = make_job(tmp_path)
        await store.create(job)

        adapter = ScriptedAdapter(failures=[PrivateContentError("private")])
        monkeypatch.setattr(download_task, "get_adapter", lambda platform: adapter)

        bot = FakeBot()
        await download_task.process_job(
            job, bot=bot, store=store, limiter=limiter, settings=settings
        )

        assert adapter.call_count == 1  # never retried
        saved = await store.get(job.job_id)
        assert saved.status == JobStatus.FAILED
        assert saved.error is not None
        assert "❌" in bot.edits[-1]
