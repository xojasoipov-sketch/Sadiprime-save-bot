"""FFmpeg-backed media processing — used only when strictly necessary.

Per spec: never re-encode media unless required. yt-dlp already selects
Telegram-compatible mp4/jpg/mp3 formats in the vast majority of cases via
the format strings in downloader/_ytdlp_common.py. This module exists for
the rare fallback case: a downloaded file is still over the configured
size limit and needs a lower-bitrate re-encode before upload, or a
container needs remuxing to be Telegram-playable inline.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from downloader.base import MediaFile, MediaKind


class ProcessingError(Exception):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def transcode_to_fit_size(
    media_file: MediaFile, *, target_max_bytes: int, timeout_seconds: int = 60
) -> MediaFile:
    """Re-encode a video to roughly fit under `target_max_bytes`.

    Only used as a last-resort fallback (see media/processor.py docstring).
    Computes a target bitrate from the file's duration and re-encodes with
    libx264 + aac. Raises ProcessingError if ffmpeg is unavailable, the
    duration is unknown, or the process fails/times out.
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

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ProcessingError(f"ffmpeg transcode timed out after {timeout_seconds}s") from exc

    if proc.returncode != 0 or not output_path.exists():
        raise ProcessingError(f"ffmpeg transcode failed: {stderr.decode(errors='replace')[-500:]}")

    new_size = output_path.stat().st_size
    old_path = media_file.path
    old_path.unlink(missing_ok=True)

    return MediaFile(
        path=output_path,
        kind=media_file.kind,
        size_bytes=new_size,
        caption=media_file.caption,
        width=media_file.width,
        height=media_file.height,
        duration_seconds=media_file.duration_seconds,
    )


def get_free_disk_bytes(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return usage.free
