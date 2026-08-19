"""Disk-space guardrails (section 16/17).

Checked before every download job starts. Protects the shared Hetzner
host from the downloader ever filling its disk and starving SadiPrime.
"""

from __future__ import annotations

from pathlib import Path

from downloader.base import DiskSpaceError
from media.cleanup import total_temp_usage_bytes
from media.processor import get_free_disk_bytes


def check_disk_capacity(
    temp_dir: Path, *, min_free_mb: int, max_temp_storage_mb: int
) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)

    free_bytes = get_free_disk_bytes(temp_dir)
    if free_bytes < min_free_mb * 1024 * 1024:
        raise DiskSpaceError(
            f"Only {free_bytes // (1024 * 1024)}MB free on host, "
            f"below required {min_free_mb}MB"
        )

    used_bytes = total_temp_usage_bytes(temp_dir)
    if used_bytes >= max_temp_storage_mb * 1024 * 1024:
        raise DiskSpaceError(
            f"media-downloader temp usage {used_bytes // (1024 * 1024)}MB "
            f"has reached its cap of {max_temp_storage_mb}MB"
        )
