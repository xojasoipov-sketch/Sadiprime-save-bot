"""Downloader adapter interface and shared error taxonomy.

Every platform adapter implements `DownloaderAdapter`. The worker never
talks to yt-dlp (or any platform-specific library) directly — it always
goes through this interface, so adding a new platform means writing one
new adapter class and registering it, not touching worker logic.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from core.config import QualityMode


class MediaKind(str, Enum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"


@dataclass
class DownloadOptions:
    quality: QualityMode = QualityMode.BEST_COMPATIBLE
    audio_only: bool = False
    max_file_size_bytes: int = 200 * 1024 * 1024
    timeout_seconds: int = 180
    output_dir: Path = field(default_factory=lambda: Path("/tmp/media-downloader"))
    #: Optional Netscape-format cookies.txt (yt-dlp's `cookiefile`).
    #: Some platforms (notably Instagram) increasingly reject anonymous
    #: requests; this lets an operator authenticate as a real account they
    #: control. Never required — adapters must work without it for
    #: platforms that don't need it.
    cookies_file: Path | None = None
    #: Force outbound requests over IPv4 (yt-dlp's `source_address`
    #: trick). Off by default — only useful on hosts with a flaky IPv6
    #: route to a platform's CDN.
    force_ipv4: bool = False


@dataclass
class MediaFile:
    path: Path
    kind: MediaKind
    size_bytes: int
    caption: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    #: yt-dlp's reported video codec (e.g. "avc1.640028", "vp09.00...").
    #: Used to catch VP9/AV1-in-mp4 streams that satisfy format/extension
    #: filters but won't autoplay inline in Telegram's iOS client — see
    #: media/processor.py's codec-fix fallback.
    vcodec: str | None = None


@dataclass
class DownloadResult:
    files: list[MediaFile]
    source_url: str
    platform: str
    title: str | None = None


# --------------------------------------------------------------------------
# Error taxonomy — the bot layer translates these into user-friendly
# messages. Never let a raw exception/stack trace reach the user.
# --------------------------------------------------------------------------


class DownloaderError(Exception):
    """Base class for all downloader-domain errors."""

    #: Whether this error is safe to retry automatically (transient).
    retryable: bool = False


class UnsupportedPlatformError(DownloaderError):
    retryable = False


class InvalidUrlError(DownloaderError):
    retryable = False


class PrivateContentError(DownloaderError):
    retryable = False


class MediaUnavailableError(DownloaderError):
    retryable = False


class DownloadTimeoutError(DownloaderError):
    retryable = True


class FileTooLargeError(DownloaderError):
    retryable = False


class DiskSpaceError(DownloaderError):
    retryable = False


class RateLimitedByPlatformError(DownloaderError):
    retryable = True


class ProcessingError(DownloaderError):
    retryable = False


class TelegramUploadError(DownloaderError):
    retryable = True


class DownloaderAdapter(ABC):
    """Interface every platform adapter must implement."""

    #: Short machine name, e.g. "instagram".
    name: str

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this adapter supports the given (already
        security-validated) URL."""

    @abstractmethod
    async def get_metadata(self, url: str) -> dict:
        """Return lightweight metadata (title, duration, is_private, ...)
        without downloading the full media."""

    @abstractmethod
    async def download(self, url: str, options: DownloadOptions) -> DownloadResult:
        """Download the media for `url` into `options.output_dir` and
        return the result. Must raise a DownloaderError subclass on
        failure — never let library-specific exceptions leak out."""

    def validate_result(self, result: DownloadResult, options: DownloadOptions) -> None:
        """Common post-download validation: at least one file, sizes
        within limits. Adapters may extend this."""

        if not result.files:
            raise MediaUnavailableError("No media files were produced")
        for f in result.files:
            if f.size_bytes > options.max_file_size_bytes:
                raise FileTooLargeError(
                    f"File {f.path.name} is {f.size_bytes} bytes, "
                    f"exceeds limit {options.max_file_size_bytes}"
                )

    async def cleanup(self, result: DownloadResult | None) -> None:
        """Remove any files produced by this adapter. Safe to call
        multiple times / with a None or partial result."""

        if result is None:
            return
        for f in result.files:
            with contextlib.suppress(OSError):
                f.path.unlink(missing_ok=True)
