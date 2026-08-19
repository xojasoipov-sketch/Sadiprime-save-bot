from __future__ import annotations

from pathlib import Path

import pytest

from downloader.base import MediaFile, MediaKind
from media.validator import (
    FileValidationError,
    ensure_within_base_dir,
    validate_dimensions,
    validate_file_signature,
    validate_media_file,
)

# Minimal valid PNG signature + IHDR chunk header — enough for `filetype`
# to positively identify it as image/png without needing a full image.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
)


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


class TestPathTraversal:
    def test_rejects_path_outside_base_dir(self, tmp_path):
        base = tmp_path / "job-1"
        base.mkdir()
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"x")
        with pytest.raises(FileValidationError):
            ensure_within_base_dir(outside, base)

    def test_allows_path_inside_base_dir(self, tmp_path):
        base = tmp_path / "job-1"
        base.mkdir()
        inside = base / "file.mp4"
        inside.write_bytes(b"x")
        ensure_within_base_dir(inside, base)  # should not raise

    def test_rejects_traversal_via_dotdot(self, tmp_path):
        base = tmp_path / "job-1"
        base.mkdir()
        (tmp_path / "secret.txt").write_bytes(b"x")
        traversal_path = base / ".." / "secret.txt"
        with pytest.raises(FileValidationError):
            ensure_within_base_dir(traversal_path, base)


class TestFileSignatureValidation:
    def test_accepts_matching_signature(self, tmp_path):
        path = _write(tmp_path / "a.png", _PNG_BYTES)
        media_file = MediaFile(path=path, kind=MediaKind.IMAGE, size_bytes=path.stat().st_size)
        validate_file_signature(media_file)  # should not raise

    def test_rejects_mismatched_declared_kind(self, tmp_path):
        # PNG bytes declared as a video -> real signature disagrees.
        path = _write(tmp_path / "a.mp4", _PNG_BYTES)
        media_file = MediaFile(path=path, kind=MediaKind.VIDEO, size_bytes=path.stat().st_size)
        with pytest.raises(FileValidationError):
            validate_file_signature(media_file)

    def test_rejects_unrecognized_content(self, tmp_path):
        path = _write(tmp_path / "a.jpg", b"not a real image, just plain text bytes")
        media_file = MediaFile(path=path, kind=MediaKind.IMAGE, size_bytes=path.stat().st_size)
        with pytest.raises(FileValidationError):
            validate_file_signature(media_file)

    def test_rejects_empty_file(self, tmp_path):
        path = _write(tmp_path / "empty.png", b"")
        media_file = MediaFile(path=path, kind=MediaKind.IMAGE, size_bytes=0)
        with pytest.raises(FileValidationError):
            validate_file_signature(media_file)

    def test_rejects_missing_file(self, tmp_path):
        media_file = MediaFile(
            path=tmp_path / "missing.png", kind=MediaKind.IMAGE, size_bytes=100
        )
        with pytest.raises(FileValidationError):
            validate_file_signature(media_file)


class TestDimensionValidation:
    def test_rejects_absurd_width(self):
        media_file = MediaFile(
            path=Path("x.png"), kind=MediaKind.IMAGE, size_bytes=1, width=999999
        )
        with pytest.raises(FileValidationError):
            validate_dimensions(media_file)

    def test_accepts_normal_dimensions(self):
        media_file = MediaFile(
            path=Path("x.png"), kind=MediaKind.IMAGE, size_bytes=1, width=1920, height=1080
        )
        validate_dimensions(media_file)  # should not raise


class TestSizeLimit:
    def test_rejects_file_over_limit(self, tmp_path):
        path = _write(tmp_path / "a.png", _PNG_BYTES)
        media_file = MediaFile(path=path, kind=MediaKind.IMAGE, size_bytes=path.stat().st_size)
        with pytest.raises(FileValidationError):
            validate_media_file(media_file, job_dir=tmp_path, max_size_bytes=1)

    def test_accepts_file_within_limit(self, tmp_path):
        path = _write(tmp_path / "a.png", _PNG_BYTES)
        media_file = MediaFile(path=path, kind=MediaKind.IMAGE, size_bytes=path.stat().st_size)
        validate_media_file(media_file, job_dir=tmp_path, max_size_bytes=10_000_000)
