"""End-to-end job pipeline: download -> validate -> upload -> cleanup.

This is the only place that ties together the downloader registry, media
validation, Telegram upload and job/lease bookkeeping. Keeping it in one
function (with small helpers) makes the state machine easy to audit:
every exit path releases the lease, the active-job slot, and the temp
directory — no matter how it fails.
"""

from __future__ import annotations

import asyncio
import time

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import (
    FSInputFile,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

from core.config import QualityMode, Settings
from core.limits import Limiter
from core.logging import get_logger
from downloader.base import (
    DownloaderError,
    DownloadOptions,
    DownloadResult,
    MediaFile,
    MediaKind,
    MediaUnavailableError,
)
from downloader.registry import get_adapter
from media.cleanup import cleanup_job_dir, job_dir_for
from media.processor import ProcessingError as CompressionError
from media.processor import ffmpeg_available, transcode_to_fit_size
from media.validator import FileValidationError, validate_media_file
from messages.registry import t
from worker.services.disk import check_disk_capacity
from worker.services.job_store import Job, JobStatus, JobStore

logger = get_logger(component="worker.download")

_ERROR_MESSAGE_KEYS: dict[type[Exception], str] = {}


def _error_key(exc: Exception) -> str:
    from core.security import InvalidUrlError as SecurityInvalidUrlError
    from downloader.base import (
        DiskSpaceError,
        DownloadTimeoutError,
        FileTooLargeError,
        MediaUnavailableError,
        PrivateContentError,
        RateLimitedByPlatformError,
        TelegramUploadError,
        UnsupportedPlatformError,
    )

    mapping = [
        (PrivateContentError, "error_private"),
        (FileTooLargeError, "error_too_large"),
        (DownloadTimeoutError, "error_timeout"),
        (DiskSpaceError, "error_generic"),
        (RateLimitedByPlatformError, "error_rate_limited"),
        (MediaUnavailableError, "error_download_failed"),
        (TelegramUploadError, "error_generic"),
        (UnsupportedPlatformError, "error_unsupported_link"),
        (SecurityInvalidUrlError, "error_invalid_url"),
        (FileValidationError, "error_download_failed"),
    ]
    for exc_type, key in mapping:
        if isinstance(exc, exc_type):
            return key
    return "error_generic"


async def _safe_edit(bot: Bot, chat_id: int, message_id: int | None, text: str) -> None:
    if message_id is None:
        return
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
    except TelegramAPIError as exc:
        logger.warning("status_edit_failed", chat_id=chat_id, error=str(exc))


async def _compress_oversized_videos(
    files: list[MediaFile],
    *,
    max_size_bytes: int,
    timeout_seconds: int,
    log: structlog.stdlib.BoundLogger,
) -> list[MediaFile]:
    """Best-effort: re-encode any oversized VIDEO file to fit under the
    limit before the size check gets a chance to reject it outright.
    Images/audio are never touched (audio is already small; images have
    no comparable "reduce bitrate" knob). Leaves a file exactly as-is if
    ffmpeg is unavailable, duration is unknown, or the transcode itself
    fails — the normal too-large error path handles it from there."""

    if not ffmpeg_available():
        return files

    result: list[MediaFile] = []
    for media_file in files:
        if media_file.size_bytes > max_size_bytes and media_file.kind == MediaKind.VIDEO:
            try:
                log.info(
                    "compress_started", file=media_file.path.name, size_bytes=media_file.size_bytes
                )
                compressed = await transcode_to_fit_size(
                    media_file, target_max_bytes=max_size_bytes, timeout_seconds=timeout_seconds
                )
                log.info(
                    "compress_completed", file=compressed.path.name, size_bytes=compressed.size_bytes
                )
                result.append(compressed)
                continue
            except CompressionError as exc:
                log.warning("compress_failed", file=media_file.path.name, error=str(exc))
        result.append(media_file)
    return result


async def _heartbeat_loop(store: JobStore, job_id: str, ttl_seconds: int) -> None:
    interval = max(5, ttl_seconds // 2)
    try:
        while True:
            await asyncio.sleep(interval)
            await store.renew_lease(job_id, ttl_seconds)
    except asyncio.CancelledError:
        pass


async def _upload_result(bot: Bot, job: Job, result: DownloadResult, lang: str) -> None:
    files = result.files
    if len(files) == 1:
        media = files[0]
        input_file = FSInputFile(media.path)
        caption = f"{t(lang, 'complete')} — {result.title}" if result.title else t(lang, "complete")
        if media.kind == MediaKind.VIDEO:
            await bot.send_video(job.chat_id, input_file, caption=caption)
        elif media.kind == MediaKind.AUDIO:
            await bot.send_audio(job.chat_id, input_file, caption=caption)
        else:
            await bot.send_photo(job.chat_id, input_file, caption=caption)
        return

    # Carousel / multi-item result -> Telegram media group (max 10 items).
    group_items: list[
        InputMediaAudio | InputMediaDocument | InputMediaPhoto | InputMediaVideo
    ] = []
    for media in files[:10]:
        input_file = FSInputFile(media.path)
        if media.kind == MediaKind.VIDEO:
            group_items.append(InputMediaVideo(media=input_file))
        else:
            group_items.append(InputMediaPhoto(media=input_file))

    if group_items:
        await bot.send_media_group(job.chat_id, media=group_items)

    # Anything beyond Telegram's 10-item media group cap is sent separately.
    for media in files[10:]:
        input_file = FSInputFile(media.path)
        if media.kind == MediaKind.VIDEO:
            await bot.send_video(job.chat_id, input_file)
        elif media.kind == MediaKind.AUDIO:
            await bot.send_audio(job.chat_id, input_file)
        else:
            await bot.send_photo(job.chat_id, input_file)


async def process_job(
    job: Job,
    *,
    bot: Bot,
    store: JobStore,
    limiter: Limiter,
    settings: Settings,
    lang: str = "uz",
) -> None:
    log = logger.bind(job_id=job.job_id, platform=job.platform, user_id=job.user_id)
    job_dir = job_dir_for(settings.temp_dir, job.job_id)
    result: DownloadResult | None = None

    await store.acquire_lease(job.job_id, settings.job_lease_seconds)
    heartbeat = asyncio.create_task(
        _heartbeat_loop(store, job.job_id, settings.job_lease_seconds)
    )

    max_attempts = 3
    try:
        for attempt in range(1, max_attempts + 1):
            job.attempt = attempt
            try:
                job.status = JobStatus.DOWNLOADING
                job.started_at = job.started_at or time.time()
                await store.save(job)
                await _safe_edit(bot, job.chat_id, job.status_message_id, t(lang, "downloading"))
                log.info("download_started", attempt=attempt)

                check_disk_capacity(
                    settings.temp_dir,
                    min_free_mb=settings.min_free_disk_mb,
                    max_temp_storage_mb=settings.max_temp_storage_mb,
                )

                adapter = get_adapter(job.platform)
                quality = (
                    QualityMode[job.quality]
                    if job.quality in QualityMode.__members__
                    else settings.default_quality
                )
                options = DownloadOptions(
                    quality=quality,
                    audio_only=job.audio_only,
                    max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024,
                    timeout_seconds=settings.download_timeout_seconds,
                    output_dir=job_dir,
                    cookies_file=settings.cookies_file,
                )
                result = await asyncio.wait_for(
                    adapter.download(job.url, options),
                    timeout=settings.job_timeout_seconds,
                )
                if not result.files:
                    raise MediaUnavailableError("No media files were produced")
                log.info("download_completed", files=len(result.files))

                job.status = JobStatus.PROCESSING
                await store.save(job)
                await _safe_edit(bot, job.chat_id, job.status_message_id, t(lang, "processing"))

                if settings.enable_compression_fallback:
                    # Try to fit an oversized video under the limit before
                    # the size check below gets a chance to reject it
                    # outright (spec: "optionally process/compress if
                    # configured" rather than a hard fail).
                    result.files = await _compress_oversized_videos(
                        result.files,
                        max_size_bytes=options.max_file_size_bytes,
                        timeout_seconds=settings.processing_timeout_seconds,
                        log=log,
                    )

                adapter.validate_result(result, options)
                for media_file in result.files:
                    validate_media_file(
                        media_file,
                        job_dir=job_dir,
                        max_size_bytes=options.max_file_size_bytes,
                    )
                log.info("processing_completed")

                job.status = JobStatus.UPLOADING
                await store.save(job)
                await _safe_edit(bot, job.chat_id, job.status_message_id, t(lang, "uploading"))
                await asyncio.wait_for(
                    _upload_result(bot, job, result, lang),
                    timeout=settings.upload_timeout_seconds,
                )
                log.info("upload_completed")

                job.status = JobStatus.COMPLETED
                job.completed_at = time.time()
                await store.save(job)
                await _safe_edit(bot, job.chat_id, job.status_message_id, t(lang, "complete"))
                await store.record_completion(job.platform, success=True)
                return

            except TelegramRetryAfter as exc:
                log.warning("telegram_rate_limited", retry_after=exc.retry_after)
                await asyncio.sleep(min(exc.retry_after, 30))
                continue

            except DownloaderError as exc:
                log.warning("job_attempt_failed", attempt=attempt, error=str(exc), retryable=exc.retryable)
                if exc.retryable and attempt < max_attempts:
                    await asyncio.sleep(2**attempt)
                    continue
                await _fail_job(bot, job, store, exc, lang, log)
                return

            except (TimeoutError, FileValidationError, TelegramAPIError) as exc:
                log.warning("job_attempt_failed", attempt=attempt, error=str(exc))
                await _fail_job(bot, job, store, exc, lang, log)
                return

            except Exception as exc:  # noqa: BLE001 - last-resort guard, never leak to user
                log.error("job_unexpected_error", error=str(exc), exc_info=True)
                await _fail_job(bot, job, store, exc, lang, log)
                return

        # Exhausted retries without an explicit failure branch above.
        await _fail_job(bot, job, store, RuntimeError("Max attempts exhausted"), lang, log)

    finally:
        heartbeat.cancel()
        await store.release_lease(job.job_id)
        await limiter.release_active_job(job.user_id, job.job_id)
        cleanup_job_dir(settings.temp_dir, job.job_id)
        log.info("job_finished", status=job.status.value)


async def _fail_job(
    bot: Bot, job: Job, store: JobStore, exc: Exception, lang: str, log: object
) -> None:
    job.status = JobStatus.FAILED
    job.error = str(exc)[:500]
    job.completed_at = time.time()
    await store.save(job)
    await _safe_edit(bot, job.chat_id, job.status_message_id, t(lang, _error_key(exc)))
    await store.record_completion(job.platform, success=False)
