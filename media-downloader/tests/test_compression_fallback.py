"""Unit tests for worker.tasks.download._apply_local_media_fixes.

ffmpeg itself is never invoked here — transcode_to_fit_size,
transcode_to_compatible_codec, and ffmpeg_available are monkeypatched, so
this only tests the *decision* logic (which files get which fix attempt,
and how failures are handled), not the actual encode. See
media/processor.py for the real ffmpeg invocation, which isn't
independently unit-tested (see README "Remaining limitations").
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.logging import get_logger
from downloader.base import MediaFile, MediaKind
from media.processor import ProcessingError
from worker.tasks import download as download_task

_MAX_SIZE = 1000


def make_file(kind: MediaKind, size_bytes: int, name: str = "f", vcodec: str | None = None) -> MediaFile:
    return MediaFile(path=Path(f"/tmp/{name}"), kind=kind, size_bytes=size_bytes, vcodec=vcodec)


@pytest.fixture
def log():
    return get_logger(component="test")


@pytest.fixture(autouse=True)
def _no_codec_fix_by_default(monkeypatch):
    # Most of these tests only exercise the size-fix path; keep codec-fix
    # a deliberate no-op unless a test overrides it.
    async def fake_codec_fix(*a, **k):
        raise AssertionError("transcode_to_compatible_codec should not be called here")

    monkeypatch.setattr(download_task, "transcode_to_compatible_codec", fake_codec_fix)


class TestSizeFix:
    async def test_skips_files_within_limit(self, monkeypatch, log):
        async def fake_transcode(*a, **k):
            raise AssertionError("should not be called")

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        files = [make_file(MediaKind.VIDEO, 500)]
        result = await download_task._apply_local_media_fixes(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == files

    async def test_skips_non_video_files_even_if_oversized(self, monkeypatch, log):
        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)

        async def fake_transcode(*a, **k):
            raise AssertionError("should not be called for non-video")

        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        files = [make_file(MediaKind.IMAGE, 5000), make_file(MediaKind.AUDIO, 5000)]
        result = await download_task._apply_local_media_fixes(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == files

    async def test_skips_everything_when_ffmpeg_unavailable(self, monkeypatch, log):
        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: False)

        files = [make_file(MediaKind.VIDEO, 5000)]
        result = await download_task._apply_local_media_fixes(
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
        result = await download_task._apply_local_media_fixes(
            files, max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [compressed]

    async def test_keeps_original_file_when_transcode_fails(self, monkeypatch, log):
        async def fake_transcode(*a, **k):
            raise ProcessingError("unknown duration")

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_transcode)

        original = make_file(MediaKind.VIDEO, 5000, name="original")
        result = await download_task._apply_local_media_fixes(
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
        result = await download_task._apply_local_media_fixes(
            [small, big], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [small, compressed]


class TestCodecFix:
    async def test_fixes_incompatible_codec(self, monkeypatch, log):
        fixed = make_file(MediaKind.VIDEO, 500, name="fixed", vcodec="avc1")

        async def fake_codec_fix(media_file, *, timeout_seconds):
            return fixed

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_compatible_codec", fake_codec_fix)

        vp9_file = make_file(MediaKind.VIDEO, 500, name="vp9", vcodec="vp09.00.10.08")
        result = await download_task._apply_local_media_fixes(
            [vp9_file], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [fixed]

    async def test_avc1_codec_is_not_touched(self, monkeypatch, log):
        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)

        avc_file = make_file(MediaKind.VIDEO, 500, name="avc", vcodec="avc1.640028")
        result = await download_task._apply_local_media_fixes(
            [avc_file], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [avc_file]

    async def test_unknown_codec_is_not_touched(self, monkeypatch, log):
        # Conservative: no vcodec info at all -> never guess, never transcode.
        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)

        unknown_file = make_file(MediaKind.VIDEO, 500, name="unknown", vcodec=None)
        result = await download_task._apply_local_media_fixes(
            [unknown_file], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [unknown_file]

    async def test_codec_fix_failure_still_allows_size_fix_to_run(self, monkeypatch, log):
        async def failing_codec_fix(*a, **k):
            raise ProcessingError("ffmpeg crashed")

        compressed = make_file(MediaKind.VIDEO, 800, name="compressed", vcodec="avc1")

        async def fake_size_fix(media_file, *, target_max_bytes, timeout_seconds):
            return compressed

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_compatible_codec", failing_codec_fix)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_size_fix)

        oversized_vp9 = make_file(
            MediaKind.VIDEO, 5000, name="oversized_vp9", vcodec="vp09.00.10.08"
        )
        result = await download_task._apply_local_media_fixes(
            [oversized_vp9], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        # Codec fix failed, but the (still-oversized, still-vp9) file
        # falls through to the size-fix path regardless.
        assert result == [compressed]

    async def test_codec_fix_then_still_oversized_runs_size_fix_too(self, monkeypatch, log):
        codec_fixed_but_big = make_file(
            MediaKind.VIDEO, 5000, name="codec_fixed", vcodec="avc1"
        )
        final = make_file(MediaKind.VIDEO, 800, name="final", vcodec="avc1")

        async def fake_codec_fix(*a, **k):
            return codec_fixed_but_big

        async def fake_size_fix(media_file, *, target_max_bytes, timeout_seconds):
            assert media_file == codec_fixed_but_big
            return final

        monkeypatch.setattr(download_task, "ffmpeg_available", lambda: True)
        monkeypatch.setattr(download_task, "transcode_to_compatible_codec", fake_codec_fix)
        monkeypatch.setattr(download_task, "transcode_to_fit_size", fake_size_fix)

        vp9_and_oversized = make_file(
            MediaKind.VIDEO, 5000, name="vp9_big", vcodec="vp09.00.10.08"
        )
        result = await download_task._apply_local_media_fixes(
            [vp9_and_oversized], max_size_bytes=_MAX_SIZE, timeout_seconds=30, log=log
        )

        assert result == [final]
