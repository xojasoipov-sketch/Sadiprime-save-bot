from __future__ import annotations

from pathlib import Path

import pytest

from downloader.base import MediaFile, MediaKind
from media.processor import needs_codec_fix


def make_file(kind: MediaKind, vcodec: str | None) -> MediaFile:
    return MediaFile(path=Path("f"), kind=kind, size_bytes=100, vcodec=vcodec)


class TestNeedsCodecFix:
    @pytest.mark.parametrize("vcodec", ["avc1.640028", "avc1", "h264", "AVC1.4D401F"])
    def test_compatible_codecs_do_not_need_a_fix(self, vcodec):
        assert needs_codec_fix(make_file(MediaKind.VIDEO, vcodec)) is False

    @pytest.mark.parametrize("vcodec", ["vp09.00.10.08", "vp9", "av01.0.05M.08", "hev1.1.6.L93.90"])
    def test_incompatible_codecs_need_a_fix(self, vcodec):
        assert needs_codec_fix(make_file(MediaKind.VIDEO, vcodec)) is True

    def test_missing_vcodec_is_never_flagged(self):
        # Conservative: no info at all -> never guess, never transcode.
        assert needs_codec_fix(make_file(MediaKind.VIDEO, None)) is False

    def test_non_video_files_are_never_flagged(self):
        assert needs_codec_fix(make_file(MediaKind.IMAGE, "vp09.00.10.08")) is False
        assert needs_codec_fix(make_file(MediaKind.AUDIO, "vp09.00.10.08")) is False
