"""Shared yt-dlp-backed adapter implementation.

Instagram, TikTok, YouTube and Pinterest are all handled through yt-dlp,
which already implements robust, actively-maintained public extractors for
these platforms. Per-platform adapters subclass `YtDlpAdapter` and only
override format-selection / carousel handling where their platform needs
something different.

Only publicly accessible content is ever requested — no cookies, no login,
no authentication bypass. yt-dlp is run with network access restricted to
what it needs and with generous but bounded timeouts.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from pathlib import Path
from typing import Any

import yt_dlp

from core.config import QualityMode
from core.security import sanitize_filename
from downloader.base import (
    BotDetectionError,
    DownloaderAdapter,
    DownloadOptions,
    DownloadResult,
    DownloadTimeoutError,
    MediaFile,
    MediaKind,
    MediaUnavailableError,
    PrivateContentError,
    ProcessingError,
    RateLimitedByPlatformError,
)

# Checked first and separately from _PRIVATE_MARKERS: YouTube's own
# anti-bot check ("Sign in to confirm you're not a bot") is a
# request-level flag, not the video actually being private — grouping it
# under "private" told users a specific public video was restricted when
# the real cause is YouTube distrusting the request (common on datacenter
# IPs like a VPS). See downloader/base.py:BotDetectionError.
_BOT_CHECK_MARKERS = ("sign in to confirm",)

_PRIVATE_MARKERS = (
    "private",
    "login required",
    "requires authentication",
    "this account is private",
)

_UNAVAILABLE_MARKERS = (
    "unavailable",
    "not available",
    "removed",
    "does not exist",
    "404",
)

_RATE_LIMIT_MARKERS = ("429", "rate-limit", "rate limit", "too many requests")


def _quality_format_string(quality: QualityMode, *, audio_only: bool) -> str:
    if audio_only:
        return "bestaudio/best"

    # Every preset prefers an avc1/h264 video codec first: Instagram and
    # TikTok both sometimes serve VP9-in-mp4, which satisfies an
    # [ext=mp4] filter but won't autoplay inline in Telegram's iOS
    # client. Preferring the codec explicitly (not just BEST_COMPATIBLE)
    # avoids that at the source; media/processor.py's codec-fix fallback
    # is the safety net for when yt-dlp has no avc1 option to offer.
    presets = {
        QualityMode.LOW: (
            "worst[vcodec^=avc1][ext=mp4]/worst[ext=mp4]/worst"
        ),
        QualityMode.MEDIUM: (
            "best[height<=480][vcodec^=avc1][ext=mp4]/"
            "best[height<=480][ext=mp4]/best[height<=480]/best"
        ),
        QualityMode.HIGH: (
            "best[height<=1080][vcodec^=avc1][ext=mp4]/"
            "best[height<=1080][ext=mp4]/best[height<=1080]/best"
        ),
        QualityMode.BEST_COMPATIBLE: (
            "best[ext=mp4][vcodec^=avc1][acodec^=mp4a]/"
            "best[ext=mp4][vcodec^=avc1]/best[ext=mp4]/best"
        ),
    }
    return presets[quality]


class YtDlpAdapter(DownloaderAdapter):
    """Base adapter that drives yt-dlp for a single platform."""

    #: Extra yt-dlp options a subclass can override (e.g. playlist behavior).
    extra_ydl_opts: dict[str, Any] = {}

    def _base_ydl_opts(self, options: DownloadOptions, job_dir: Path) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,  # never silently pull whole playlists
            "outtmpl": str(job_dir / "%(id)s.%(ext)s"),
            "format": _quality_format_string(options.quality, audio_only=options.audio_only),
            "restrictfilenames": True,
            "noprogress": True,
            "socket_timeout": min(30, options.timeout_seconds),
            "retries": 2,
            # The Python API has no implicit default for either of these
            # (unlike yt-dlp's CLI) — must be set explicitly to have any
            # effect. fragment_retries covers segmented/HLS delivery
            # (common on IG reels/stories); throttledratelimit makes
            # yt-dlp abort and retry a connection that's been silently
            # throttled below this speed instead of just running slow
            # until the outer timeout.
            "fragment_retries": 10,
            "throttledratelimit": 51_200,  # 50 KB/s
            "max_filesize": options.max_file_size_bytes,
            "merge_output_format": "mp4",
        }
        if options.force_ipv4:
            # Opt-in: some VPS hosts have a flaky IPv6 route to a given
            # CDN while IPv4 is fine. Off by default since it can only
            # hurt on an IPv6-only host.
            opts["source_address"] = "0.0.0.0"
        if options.audio_only:
            # Force a real audio container (mp3) via ffmpeg: the raw
            # "bestaudio" stream is often .webm/.m4a, which _kind_for_ext
            # would otherwise misclassify as video.
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        if options.cookies_file and options.cookies_file.exists():
            # Some platforms (Instagram in particular) increasingly reject
            # anonymous requests. Missing/unset is the common case and is
            # silently skipped — cookies are opt-in, never required.
            opts["cookiefile"] = str(options.cookies_file)
        opts.update(self.extra_ydl_opts)
        return opts

    async def get_metadata(self, url: str) -> dict:
        loop = asyncio.get_running_loop()
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
        try:
            info = await loop.run_in_executor(
                None, functools.partial(self._extract_info, url, opts)
            )
        except yt_dlp.utils.DownloadError as exc:
            raise self._translate_error(exc) from exc
        return info or {}

    def _extract_info(self, url: str, opts: dict[str, Any]) -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def download(self, url: str, options: DownloadOptions) -> DownloadResult:
        job_dir = options.output_dir
        job_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = self._base_ydl_opts(options, job_dir)

        loop = asyncio.get_running_loop()
        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(
                    None, functools.partial(self._run_download, url, ydl_opts)
                ),
                timeout=options.timeout_seconds,
            )
        except TimeoutError as exc:
            raise DownloadTimeoutError(f"Download timed out after {options.timeout_seconds}s") from exc
        except yt_dlp.utils.DownloadError as exc:
            raise self._translate_error(exc) from exc

        files = self._collect_files(info, job_dir)
        if not files:
            raise MediaUnavailableError("No downloadable media found for this URL")

        return DownloadResult(
            files=files,
            source_url=url,
            platform=self.name,
            title=(info or {}).get("title"),
        )

    def _run_download(self, url: str, ydl_opts: dict[str, Any]) -> dict:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)

    def _collect_files(self, info: dict | None, job_dir: Path) -> list[MediaFile]:
        if not info:
            return []

        entries = info.get("entries") if info.get("_type") == "playlist" else [info]
        entries = [e for e in (entries or []) if e]

        files: list[MediaFile] = []
        for entry in entries:
            requested = entry.get("requested_downloads") or []
            candidates = requested if requested else [entry]
            for cand in candidates:
                filepath = cand.get("filepath") or cand.get("_filename")
                if not filepath:
                    continue
                path = Path(filepath)
                if not path.exists():
                    continue
                # Re-home into job_dir with a sanitized name in case yt-dlp
                # wrote outside outtmpl expectations (defense in depth).
                safe_name = sanitize_filename(path.name)
                target = job_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
                if path != target:
                    path.replace(target)
                    path = target
                kind = self._kind_for_ext(path.suffix.lower())
                files.append(
                    MediaFile(
                        path=path,
                        kind=kind,
                        size_bytes=path.stat().st_size,
                        caption=entry.get("title"),
                        width=entry.get("width"),
                        height=entry.get("height"),
                        duration_seconds=entry.get("duration"),
                        vcodec=cand.get("vcodec") or entry.get("vcodec"),
                    )
                )
        return files

    @staticmethod
    def _kind_for_ext(ext: str) -> MediaKind:
        if ext in {".mp4", ".mov", ".mkv", ".webm"}:
            return MediaKind.VIDEO
        if ext in {".mp3", ".m4a", ".aac", ".opus", ".ogg"}:
            return MediaKind.AUDIO
        return MediaKind.IMAGE

    @staticmethod
    def _translate_error(exc: yt_dlp.utils.DownloadError) -> Exception:
        message = str(exc).lower()
        if any(marker in message for marker in _BOT_CHECK_MARKERS):
            return BotDetectionError("The platform flagged this request as automated traffic")
        if any(marker in message for marker in _PRIVATE_MARKERS):
            return PrivateContentError("This content is private or requires login")
        if any(marker in message for marker in _RATE_LIMIT_MARKERS):
            return RateLimitedByPlatformError("The platform is rate-limiting requests")
        if any(marker in message for marker in _UNAVAILABLE_MARKERS):
            return MediaUnavailableError("The media could not be found or is unavailable")
        return ProcessingError(f"Download failed: {exc}")
