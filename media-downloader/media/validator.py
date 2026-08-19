"""Post-download file validation.

Never trust yt-dlp's reported extension or Telegram's MIME guess alone —
validate actual file signatures ("magic bytes") before ever touching or
sending a downloaded file. Also guards against path traversal (a
downloaded file resolving outside the job's temp directory) and absurd
image/video dimensions (a crude decompression-bomb guard).
"""

from __future__ import annotations

from pathlib import Path

import filetype

from downloader.base import MediaFile, MediaKind

_ALLOWED_MIME_PREFIXES: dict[MediaKind, tuple[str, ...]] = {
    MediaKind.VIDEO: ("video/",),
    MediaKind.IMAGE: ("image/",),
    MediaKind.AUDIO: ("audio/", "video/"),  # some audio containers are detected as video/*
}

# Crude decompression-bomb guard: reject absurdly large declared dimensions.
_MAX_PIXEL_DIMENSION = 8192


class FileValidationError(Exception):
    pass


def ensure_within_base_dir(path: Path, base_dir: Path) -> None:
    """Path-traversal guard: raise if `path` does not resolve inside base_dir."""

    resolved = path.resolve()
    base = base_dir.resolve()
    if base not in resolved.parents and resolved != base:
        raise FileValidationError(f"Path {resolved} escapes base directory {base}")


def validate_file_signature(media_file: MediaFile) -> None:
    """Validate the file's real content type via magic-byte sniffing."""

    if not media_file.path.exists():
        raise FileValidationError(f"File does not exist: {media_file.path}")

    if media_file.size_bytes <= 0:
        raise FileValidationError("File is empty")

    kind = filetype.guess(str(media_file.path))
    if kind is None:
        raise FileValidationError(
            f"Could not determine file type for {media_file.path.name}; refusing to send"
        )

    allowed_prefixes = _ALLOWED_MIME_PREFIXES.get(media_file.kind, ())
    if not any(kind.mime.startswith(prefix) for prefix in allowed_prefixes):
        raise FileValidationError(
            f"File {media_file.path.name} has unexpected type {kind.mime} "
            f"for declared kind {media_file.kind}"
        )


def validate_dimensions(media_file: MediaFile) -> None:
    if media_file.width and media_file.width > _MAX_PIXEL_DIMENSION:
        raise FileValidationError(f"Width {media_file.width} exceeds sanity limit")
    if media_file.height and media_file.height > _MAX_PIXEL_DIMENSION:
        raise FileValidationError(f"Height {media_file.height} exceeds sanity limit")


def validate_media_file(media_file: MediaFile, *, job_dir: Path, max_size_bytes: int) -> None:
    ensure_within_base_dir(media_file.path, job_dir)

    if media_file.size_bytes > max_size_bytes:
        raise FileValidationError(
            f"File {media_file.path.name} ({media_file.size_bytes}B) exceeds "
            f"max size {max_size_bytes}B"
        )

    validate_dimensions(media_file)
    validate_file_signature(media_file)


__all__ = [
    "FileValidationError",
    "ensure_within_base_dir",
    "validate_dimensions",
    "validate_file_signature",
    "validate_media_file",
]
