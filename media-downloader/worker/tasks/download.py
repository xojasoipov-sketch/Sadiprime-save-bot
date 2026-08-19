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
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)

from bot.services.song_id import store_snippet
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
from media.processor import (
    extract_audio_snippet,
    ffmpeg_available,
    needs_codec_fix,
    transcode_to_compatible_codec,
    transcode_to_fit_size,
)
from media.validator import FileValidationError, validate_media_file
from messages.registry import t
from worker.services.disk import check_disk_capacity
from worker.services.job_store import Job, JobStatus, JobStore

logger = get_logger(component="worker.download")

_ERROR_MESSAGE_KEYS: dict[type[Exception], str] = {}


def _error_key(exc: Exception) -> str:
    from core.security import InvalidUrlError as SecurityInvalidUrlError
    from downloader.base import (
        BotDetectionError,
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
        (BotDetectionError, "error_bot_check"),
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


_ADMIN_ALERT_COOLDOWN_SECONDS = 600  # 10 minutes, per (platform, error type)


async def _notify_admins_of_failure(
    bot: Bot,
    store: JobStore,
    settings: Settings,
    job: Job,
    exc: Exception,
    log: structlog.stdlib.BoundLogger,
) -> None:
    """Best-effort proactive DM to admins on a job failure.

    Deduplicated per (platform, error type) with a cooldown window so a
    platform-wide outage (Instagram cookies expiring, yt-dlp needing an
    update, ...) sends one alert rather than one per failed job. A failed
    DM (blocked bot, etc.) is logged and never re-raised — alerting must
    never break the job pipeline it's reporting on.
    """

    if not settings.admin_user_ids:
        return

    error_type = type(exc).__name__
    dedup_key = f"md:adminalert:{job.platform}:{error_type}"
    # NX: only the first caller within the cooldown window actually sends.
    sent_first = await store.redis.set(
        dedup_key, "1", nx=True, ex=_ADMIN_ALERT_COOLDOWN_SECONDS
    )
    if not sent_first:
        return

    text = (
        "⚠️ Job failed\n"
        f"platform: {job.platform}\n"
        f"error: {error_type}: {str(exc)[:300]}\n"
        f"url: {job.url[:200]}\n"
        f"attempt: {job.attempt}\n"
        f"job_id: {job.job_id}"
    )
    for admin_id in settings.admin_user_ids:
        try:
            await bot.send_message(admin_id, text)
        except TelegramAPIError as alert_exc:
            log.warning("admin_alert_failed", admin_id=admin_id, error=str(alert_exc))


async def _apply_local_media_fixes(
    files: list[MediaFile],
    *,
    max_size_bytes: int,
    timeout_seconds: int,
    log: structlog.stdlib.BoundLogger,
) -> list[MediaFile]:
    """Best-effort local ffmpeg fallbacks for VIDEO files, tried before the
    size/type checks get a chance to reject a file outright:

      1. codec fix — yt-dlp reported a video codec (VP9/AV1-in-mp4, which
         Instagram/TikTok sometimes serve) that won't autoplay inline in
         Telegram's iOS client, even though it passed our format filters.
      2. size fix — still (or now, post-re-encode) over the configured
         limit, so re-encode at a bitrate that fits.

    Images/audio are never touched. Leaves a file exactly as-is if ffmpeg
    is unavailable or a given step fails — the normal validation error
    path handles it from there, it just never gets a silent free pass."""

    if not ffmpeg_available():
        return files

    result: list[MediaFile] = []
    for media_file in files:
        current = media_file

        if needs_codec_fix(current):
            try:
                log.info("codec_fix_started", file=current.path.name, vcodec=current.vcodec)
                current = await transcode_to_compatible_codec(
                    current, timeout_seconds=timeout_seconds
                )
                log.info(
                    "codec_fix_completed", file=current.path.name, size_bytes=current.size_bytes
                )
            except CompressionError as exc:
                log.warning("codec_fix_failed", file=current.path.name, error=str(exc))

        if current.kind == MediaKind.VIDEO and current.size_bytes > max_size_bytes:
            try:
                log.info(
                    "compress_started", file=current.path.name, size_bytes=current.size_bytes
                )
                current = await transcode_to_fit_size(
                    current, target_max_bytes=max_size_bytes, timeout_seconds=timeout_seconds
                )
                log.info(
                    "compress_completed", file=current.path.name, size_bytes=current.size_bytes
                )
            except CompressionError as exc:
                log.warning("compress_failed", file=current.path.name, error=str(exc))

        result.append(current)
    return result


async def _heartbeat_loop(store: JobStore, job_id: str, ttl_seconds: int) -> None:
    interval = max(5, ttl_seconds // 2)
    try:
        while True:
            await asyncio.sleep(interval)
            await store.renew_lease(job_id, ttl_seconds)
    except asyncio.CancelledError:
        pass


def _int_duration(seconds: float | None) -> int | None:
    """Telegram's Bot API wants an integer second count; MediaFile carries
    a float (as reported by yt-dlp). None passes through unchanged."""

    return int(seconds) if seconds else None


def _song_id_keyboard(job_id: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "song_id_button"), callback_data=f"songid:{job_id}")]
        ]
    )


async def _upload_result(
    bot: Bot, job: Job, result: DownloadResult, lang: str, settings: Settings
) -> None:
    files = result.files
    if len(files) == 1:
        media = files[0]
        input_file = FSInputFile(media.path)
        caption = f"{t(lang, 'complete')} — {result.title}" if result.title else t(lang, "complete")
        if media.kind == MediaKind.VIDEO:
            # Only offer song identification for a single-video result and
            # only when an AudD.io token is configured — silently absent
            # otherwise, same optional-feature pattern as COOKIES_FILE.
            reply_markup = (
                _song_id_keyboard(job.job_id, lang) if settings.audd_api_token else None
            )
            # width/height/duration MUST be passed explicitly: without them
            # Telegram clients don't know the real aspect ratio at render
            # time and guess a default preview box, which shows up as a
            # squished/letterboxed video in the chat list until tapped.
            await bot.send_video(
                job.chat_id,
                input_file,
                caption=caption,
                width=media.width,
                height=media.height,
                duration=_int_duration(media.duration_seconds),
                supports_streaming=True,
                reply_markup=reply_markup,
            )
        elif media.kind == MediaKind.AUDIO:
            await bot.send_audio(
                job.chat_id,
                input_file,
                caption=caption,
                duration=_int_duration(media.duration_seconds),
            )
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
            group_items.append(
                InputMediaVideo(
                    media=input_file,
                    width=media.width,
                    height=media.height,
                    duration=_int_duration(media.duration_seconds),
                    supports_streaming=True,
                )
            )
        else:
            group_items.append(InputMediaPhoto(media=input_file))

    if group_items:
        await bot.send_media_group(job.chat_id, media=group_items)

    # Anything beyond Telegram's 10-item media group cap is sent separately.
    for media in files[10:]:
        input_file = FSInputFile(media.path)
        if media.kind == MediaKind.VIDEO:
            await bot.send_video(
                job.chat_id,
                input_file,
                width=media.width,
                height=media.height,
                duration=_int_duration(media.duration_seconds),
                supports_streaming=True,
            )
        elif media.kind == MediaKind.AUDIO:
            await bot.send_audio(
                job.chat_id, input_file, duration=_int_duration(media.duration_seconds)
            )
        else:
            await bot.send_photo(job.chat_id, input_file)


async def _store_song_id_snippet(
    store: JobStore,
    job: Job,
    result: DownloadResult,
    settings: Settings,
    log: structlog.stdlib.BoundLogger,
) -> None:
    """Extract a short audio clip from the uploaded video and stash it in
    Redis under the job id, for the "identify song" button to consume
    later. Never raises — a failure here must not fail the job itself,
    since the video has already been delivered to the user by this point.
    """

    if len(result.files) != 1 or result.files[0].kind != MediaKind.VIDEO:
        return

    try:
        snippet_path = await extract_audio_snippet(
            result.files[0],
            output_dir=result.files[0].path.parent,
            timeout_seconds=settings.processing_timeout_seconds,
        )
        audio_bytes = snippet_path.read_bytes()
        snippet_path.unlink(missing_ok=True)
        await store_snippet(store.redis, job_id=job.job_id, audio_bytes=audio_bytes)
    except Exception as exc:  # noqa: BLE001 - best-effort, never fail the job for this
        log.warning("song_id_snippet_failed", error=str(exc))


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
                    force_ipv4=settings.force_ipv4,
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
                    # Try to fix an incompatible codec and/or fit an
                    # oversized video under the limit before the checks
                    # below get a chance to reject it outright (spec:
                    # "optionally process/compress if configured" rather
                    # than a hard fail).
                    result.files = await _apply_local_media_fixes(
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
                    _upload_result(bot, job, result, lang, settings),
                    timeout=settings.upload_timeout_seconds,
                )
                log.info("upload_completed")

                if settings.audd_api_token:
                    # Best-effort: the song-id button is only useful if a
                    # snippet is waiting in Redis by the time it's tapped.
                    # Must happen before the finally block's
                    # cleanup_job_dir() deletes the source video below.
                    await _store_song_id_snippet(store, job, result, settings, log)

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
                await _fail_job(bot, job, store, settings, exc, lang, log)
                return

            except (TimeoutError, FileValidationError, TelegramAPIError) as exc:
                log.warning("job_attempt_failed", attempt=attempt, error=str(exc))
                await _fail_job(bot, job, store, settings, exc, lang, log)
                return

            except Exception as exc:  # noqa: BLE001 - last-resort guard, never leak to user
                log.error("job_unexpected_error", error=str(exc), exc_info=True)
                await _fail_job(bot, job, store, settings, exc, lang, log)
                return

        # Exhausted retries without an explicit failure branch above.
        await _fail_job(bot, job, store, settings, RuntimeError("Max attempts exhausted"), lang, log)

    finally:
        heartbeat.cancel()
        await store.release_lease(job.job_id)
        await limiter.release_active_job(job.user_id, job.job_id)
        cleanup_job_dir(settings.temp_dir, job.job_id)
        log.info("job_finished", status=job.status.value)


async def _fail_job(
    bot: Bot,
    job: Job,
    store: JobStore,
    settings: Settings,
    exc: Exception,
    lang: str,
    log: structlog.stdlib.BoundLogger,
) -> None:
    job.status = JobStatus.FAILED
    job.error = str(exc)[:500]
    job.completed_at = time.time()
    await store.save(job)
    await _safe_edit(bot, job.chat_id, job.status_message_id, t(lang, _error_key(exc)))
    await store.record_completion(job.platform, success=False)
    await _notify_admins_of_failure(bot, store, settings, job, exc, log)
