"""FFmpeg-backed media processing — used only when strictly necessary.

Per spec: never re-encode media unless required. yt-dlp already selects
Telegram-compatible mp4/jpg/mp3 formats in the vast majority of cases via
the format strings in downloader/_ytdlp_common.py. This module exists for
the fallback cases those format filters don't fully cover:

  * transcode_to_fit_size — the downloaded file is still over the
    configured size limit and needs a lower-bitrate re-encode before
    upload.
  * transcode_to_compatible_codec — yt-dlp had no avc1/h264 option to
    offer (Instagram/TikTok sometimes only serve VP9-in-mp4), which
    satisfies our [ext=mp4] format filter but won't autoplay inline in
    Telegram's iOS client.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from downloader.base import MediaFile, MediaKind

# Codecs that autoplay inline everywhere Telegram runs. Anything else
# reported by yt-dlp (vp9, vp09, av1, av01, hev1/hvc1, ...) is a
# transcode_to_compatible_codec candidate.
_COMPATIBLE_VIDEO_CODEC_PREFIXES = ("avc1", "h264")


class ProcessingError(Exception):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def needs_codec_fix(media_file: MediaFile) -> bool:
    """True if yt-dlp reported a video codec Telegram's iOS client won't
    play inline. Conservative: an unknown/missing vcodec is NOT flagged —
    only an explicitly-reported incompatible one triggers a re-encode, so
    we never transcode on a guess."""

    if media_file.kind != MediaKind.VIDEO or not media_file.vcodec:
        return False
    vcodec = media_file.vcodec.lower()
    return not vcodec.startswith(_COMPATIBLE_VIDEO_CODEC_PREFIXES)


async def _run_ffmpeg(cmd: list[str], *, output_path: Path, timeout_seconds: int) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ProcessingError(f"ffmpeg timed out after {timeout_seconds}s") from exc

    if proc.returncode != 0 or not output_path.exists():
        raise ProcessingError(f"ffmpeg failed: {stderr.decode(errors='replace')[-500:]}")


async def transcode_to_fit_size(
    media_file: MediaFile, *, target_max_bytes: int, timeout_seconds: int = 60
) -> MediaFile:
    """Re-encode a video to roughly fit under `target_max_bytes`.

    Only used as a last-resort fallback (see module docstring). Computes
    a target bitrate from the file's duration and re-encodes with libx264
    + aac. Raises ProcessingError if ffmpeg is unavailable, the duration
    is unknown, or the process fails/times out.
    """

    if media_file.kind != MediaKind.VIDEO:
        raise ProcessingError("Only video files can be transcoded to fit a size limit")
    if not ffmpeg_available():
        raise ProcessingError("ffmpeg is not available in this environment")
    if not media_file.duration_seconds or media_file.duration_seconds <= 0:
        raise ProcessingError("Unknown duration; cannot compute a target bitrate")

    # Reserve ~10% headroom for container overhead / audio track.
    target_bits = target_max_bytes * 8 * 0.9
    target_bitrate_kbps = max(200, int(target_bits / media_file.duration_seconds / 1000))

    output_path = media_file.path.with_name(f"{media_file.path.stem}_compressed.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_file.path),
        "-c:v",
        "libx264",
        "-b:v",
        f"{target_bitrate_kbps}k",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    await _run_ffmpeg(cmd, output_path=output_path, timeout_seconds=timeout_seconds)

    new_size = output_path.stat().st_size
    media_file.path.unlink(missing_ok=True)

    return MediaFile(
        path=output_path,
        kind=media_file.kind,
        size_bytes=new_size,
        caption=media_file.caption,
        width=media_file.width,
        height=media_file.height,
        duration_seconds=media_file.duration_seconds,
        vcodec="avc1",
    )


async def transcode_to_compatible_codec(
    media_file: MediaFile, *, timeout_seconds: int = 60
) -> MediaFile:
    """Re-encode a video's stream to H.264 while leaving audio untouched.

    Used when yt-dlp had no avc1/h264 format to offer at all (rather than
    the size-driven path above, which always re-encodes to libx264
    anyway). Audio is copied, not re-encoded, since only the video codec
    is the compatibility problem here.
    """

    if media_file.kind != MediaKind.VIDEO:
        raise ProcessingError("Only video files can be re-encoded for codec compatibility")
    if not ffmpeg_available():
        raise ProcessingError("ffmpeg is not available in this environment")

    output_path = media_file.path.with_name(f"{media_file.path.stem}_h264.mp4")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_file.path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    await _run_ffmpeg(cmd, output_path=output_path, timeout_seconds=timeout_seconds)

    new_size = output_path.stat().st_size
    media_file.path.unlink(missing_ok=True)

    return MediaFile(
        path=output_path,
        kind=media_file.kind,
        size_bytes=new_size,
        caption=media_file.caption,
        width=media_file.width,
        height=media_file.height,
        duration_seconds=media_file.duration_seconds,
        vcodec="avc1",
    )


def get_free_disk_bytes(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return usage.free
