"""Unit tests for worker.tasks.download._compress_oversized_videos.

ffmpeg itself is never invoked here — transcode_to_fit_size and
ffmpeg_available are monkeypatched, so this only tests the *decision*
logic (which files get a compression attempt, and how failures are
handled), not the actual encode. See media/processor.py for the real
ffmpeg invocation, which isn't independently unit-tested (see README
"Remaining limitations").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.logging import get_logger
from downloader.base import MediaFile, MediaKind
from media.processor import ProcessingError
from worker.tasks import download as download_task

_MAX_SIZE = 1000


def make_file(kind: MediaKind, size_bytes: int, name: str = "f") -> MediaFile:
    return MediaFile(path=Path(f"/tmp/{name}"), kind=kind, size_bytes=size_bytes)


@pytest.fixture
def log():
    return get_logger(component="test")


class TestCompressOversizedVideos:
    async def test_skips_files_within_limit(self, monkeypatch, log):
        called = False

        async def fake_transcode(*a, **k):
            nonlocal called
            called = True
            raise AssertionError("should not be called")

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        files = [make_file(MediaKind.VIDEO, 500)]
        result = await download_task._compress_oversized_videos(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == files
        assert not called

    async def test_skips_non_video_files_even_if_oversized(self, monkeypatch, log):
        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)

        async def fake_transcode(*a, **k):
            raise AssertionError("should not be called for non-video")

        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        files = [make_file(MediaKind.IMAGE, 5000), make_file(MediaKind.AUDIO, 5000)]
        result = await download_task._compress_oversized_videos(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == files

    async def test_skips_everything_when_ffmpeg_unavailable(self, monkeypatch, log):
        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: False)

        files = [make_file(MediaKind.VIDEO, 5000)]
        result = await download_task._compress_oversized_videos(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == files

    async def test_replaces_oversized_video_with_compressed_result(self, monkeypatch, log):
        compressed = make_file(MediaKind.VIDEO, 800, name="compressed")

        async def fake_transcode(media_file, *, target_max_bytes, timeout_seconds):
            assert target_max_bytes == _MAX_SIZE
            return compressed

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        files = [make_file(MediaKind.VIDEO, 5000, name="original")]
        result = await download_task._compress_oversized_videos(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [compressed]

    async def test_keeps_original_file_when_transcode_fails(self, monkeypatch, log):
        async def fake_transcode(*a, **k):
            raise ProcessingError("unknown duration")

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        original = make_file(MediaKind.VIDEO, 5000, name="original")
        result = await download_task._compress_oversized_videos(
            [original], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        # Still oversized, but the caller's normal size-validation path
        # handles that — this function must not raise or drop the file.
        assert result == [original]

    async def test_leaves_files_within_limit_mixed_with_oversized_ones(self, monkeypatch, log):
        compressed = make_file(MediaKind.VIDEO, 800, name="compressed")

        async def fake_transcode(*a, **k):
            return compressed

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        small = make_file(MediaKind.VIDEO, 100, name="small")
        big = make_file(MediaKind.VIDEO, 5000, name="big")
        result = await download_task._compress_oversized_videos(
            [small, big], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [small, compressed]
